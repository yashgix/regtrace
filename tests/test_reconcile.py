"""Tests for regtrace.reconcile: statuses, claims and the unexplained list."""

from __future__ import annotations

import unittest
from unittest import mock

import regtrace.reconcile as reconcile_module
from regtrace.model import Document, Instruction, Row, Version

BASE = "2020-01-01"


def _document(
    number: str = "2024-0001",
    doc_type: str = "Rule",
    publication_date: str = "2020-06-01",
    effective_on: str | None = "2021-01-01",
) -> Document:
    return Document(number, doc_type, "Final rule", "Title", publication_date, effective_on, True)


def _version(section: str, date: str, substantive: bool = True) -> Version:
    return Version(section, date, substantive)


def _reconcile(
    docs: list[Document],
    vers: list[Version],
    predict=None,
    window_days: int = 30,
    instruction_map: dict[str, list[Instruction]] | None = None,
):
    with (
        mock.patch.object(reconcile_module, "documents", return_value=docs),
        mock.patch.object(reconcile_module, "versions", return_value=vers),
    ):
        if predict is not None:
            return reconcile_module.reconcile(window_days=window_days, predict=predict)
        mapping = instruction_map or {}
        with mock.patch.object(
            reconcile_module,
            "instructions",
            side_effect=lambda number: mapping.get(number, []),
        ):
            return reconcile_module.reconcile(window_days=window_days)


class ReconcileTests(unittest.TestCase):
    def test_matched_row_claims_expected_version(self) -> None:
        docs = [_document(publication_date="2020-06-01", effective_on="2021-01-01")]
        vers = [_version("438.2", BASE), _version("438.2", "2021-01-01")]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "matched", "2021-01-01")])
        self.assertEqual(unexplained, [])

    def test_null_effective_date_uses_publication_date(self) -> None:
        docs = [_document(publication_date="2021-01-01", effective_on=None)]
        vers = [_version("438.2", BASE), _version("438.2", "2021-01-01")]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "matched", "2021-01-01")])
        self.assertEqual(unexplained, [])

    def test_before_history_takes_precedence_and_claims_nothing(self) -> None:
        docs = [_document(publication_date="2019-12-01", effective_on=BASE)]
        vers = [_version("438.2", BASE), _version("438.2", "2021-01-01")]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "before_history", None)])
        self.assertEqual(unexplained, [("438.2", "2021-01-01")])

    def test_matched_requires_a_substantive_version(self) -> None:
        docs = [_document(publication_date="2020-06-01", effective_on="2021-01-01")]
        vers = [_version("438.2", BASE), _version("438.2", "2021-01-01", substantive=False)]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "unmatched", None)])
        self.assertEqual(unexplained, [])

    def test_shifted_picks_nearest_earlier_on_tie_and_claims_that_date(self) -> None:
        docs = [_document(publication_date="2020-06-01", effective_on="2021-02-15")]
        vers = [
            _version("438.2", BASE),
            _version("438.2", "2021-02-10"),
            _version("438.2", "2021-02-20"),
        ]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "shifted", "2021-02-10")])
        self.assertEqual(unexplained, [("438.2", "2021-02-20")])

    def test_shifted_claims_publication_date_when_it_is_a_version(self) -> None:
        docs = [_document(publication_date="2020-08-01", effective_on="2021-02-15")]
        vers = [
            _version("438.2", BASE),
            _version("438.2", "2020-08-01"),
            _version("438.2", "2021-02-10"),
        ]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "shifted", "2021-02-10")])
        self.assertEqual(unexplained, [])

    def test_window_boundary_is_inclusive(self) -> None:
        docs = [_document(publication_date="2020-06-01", effective_on="2021-01-01")]
        vers = [_version("438.2", BASE), _version("438.2", "2021-02-15")]
        short_rows, short_unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"], window_days=30)
        self.assertEqual(short_rows, [Row("2024-0001", "438.2", "unmatched", None)])
        self.assertEqual(short_unexplained, [("438.2", "2021-02-15")])
        long_rows, long_unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"], window_days=45)
        self.assertEqual(long_rows, [Row("2024-0001", "438.2", "shifted", "2021-02-15")])
        self.assertEqual(long_unexplained, [])

    def test_matched_row_also_claims_the_publication_date(self) -> None:
        docs = [_document(publication_date="2020-08-01", effective_on="2021-01-01")]
        vers = [
            _version("438.2", BASE),
            _version("438.2", "2020-08-01"),
            _version("438.2", "2021-01-01"),
        ]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [Row("2024-0001", "438.2", "matched", "2021-01-01")])
        self.assertEqual(unexplained, [])

    def test_proposed_rules_are_ignored(self) -> None:
        docs = [_document(doc_type="Proposed Rule")]
        vers = [_version("438.2", BASE)]
        rows, unexplained = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual(rows, [])
        self.assertEqual(unexplained, [])

    def test_predicted_sections_are_deduplicated_and_ordered(self) -> None:
        docs = [_document()]
        vers = [_version("438.2", BASE)]
        rows, _ = _reconcile(docs, vers, predict=lambda _: ["438.10", "438.2", "438.10"])
        self.assertEqual([row.section for row in rows], ["438.2", "438.10"])
        self.assertEqual([row.status for row in rows], ["unmatched", "unmatched"])

    def test_default_prediction_uses_instruction_sections(self) -> None:
        docs = [_document()]
        vers = [_version("438.2", BASE), _version("438.2", "2021-01-01")]
        instruction = Instruction("2024-0001", 1, "Amend 438.2.", ("438.2", "438.10"))
        rows, unexplained = _reconcile(docs, vers, instruction_map={"2024-0001": [instruction]})
        self.assertEqual(
            rows,
            [
                Row("2024-0001", "438.2", "matched", "2021-01-01"),
                Row("2024-0001", "438.10", "unmatched", None),
            ],
        )
        self.assertEqual(unexplained, [])

    def test_unexplained_orders_by_date_then_section_and_skips_non_substantive(self) -> None:
        vers = [
            _version("438.2", BASE),
            _version("438.10", "2020-06-01"),
            _version("438.2", "2021-01-01"),
            _version("438.10", "2021-01-01"),
            _version("438.2", "2020-06-01", substantive=False),
        ]
        rows, unexplained = _reconcile([], vers, predict=lambda _: [])
        self.assertEqual(rows, [])
        self.assertEqual(
            unexplained,
            [
                ("438.10", "2020-06-01"),
                ("438.2", "2021-01-01"),
                ("438.10", "2021-01-01"),
            ],
        )

    def test_base_version_is_never_unexplained(self) -> None:
        vers = [_version("438.2", BASE), _version("438.10", BASE)]
        rows, unexplained = _reconcile([], vers, predict=lambda _: [])
        self.assertEqual(rows, [])
        self.assertEqual(unexplained, [])

    def test_rows_follow_document_file_order(self) -> None:
        docs = [
            _document(number="2024-0001", publication_date="2020-06-01", effective_on="2021-01-01"),
            _document(number="2024-0002", publication_date="2020-07-01", effective_on="2021-02-01"),
        ]
        vers = [_version("438.2", BASE)]
        rows, _ = _reconcile(docs, vers, predict=lambda _: ["438.2"])
        self.assertEqual([row.document for row in rows], ["2024-0001", "2024-0002"])


if __name__ == "__main__":
    unittest.main()
