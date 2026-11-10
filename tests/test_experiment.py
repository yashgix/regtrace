"""Tests for the deterministic metrics in experiment.py."""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import experiment
import regtrace.reconcile as reconcile_module
from regtrace.model import Document, Instruction, Paragraph, Part, Row, Section, Verdict, Version


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _section(section_id: str, *paragraphs: tuple[str, str]) -> Section:
    return Section(section_id, f"\u00a7 {section_id} Heading.", tuple(Paragraph(label, text) for label, text in paragraphs))


PARTS = {
    "2020-01-01": Part(
        "2020-01-01",
        {
            "438.2": _section("438.2", ("(a)", "(a) A long enough paragraph about network adequacy.")),
            "438.10": _section("438.10", ("(a)", "(a) Another paragraph about information requirements.")),
        },
    ),
    "2021-01-01": Part(
        "2021-01-01",
        {
            "438.2": _section(
                "438.2",
                ("(a)", "(a) A long enough paragraph about network adequacy."),
                ("~1", "Extra unlabeled text about something."),
            ),
            "438.10": _section("438.10", ("(a)", "(a) Another paragraph about information requirements.")),
        },
    ),
}

DOCUMENTS = [
    Document("2020-0001", "Rule", "Final rule", "Medicaid managed care", "2020-06-01", "2021-01-01", True),
    Document("2020-0002", "Proposed Rule", "Proposed rule", "Medicaid managed care", "2020-07-01", None, True),
]

VERSIONS = [
    Version("438.2", "2020-01-01", True),
    Version("438.2", "2021-01-01", True),
]

INSTRUCTION_MAP = {"2020-0001": [Instruction("2020-0001", 1, "Amend \u00a7 438.2.", ("438.2",))]}

DOCUMENT_XML = {"2020-0001": "<ROOT>See \u00a7\u00a7 438.2 and 438.10.</ROOT>", "2020-0002": None}

EXPECTED = {
    "dates": 2,
    "sections_latest": 2,
    "paragraphs_latest": 3,
    "unlabeled_latest": 1,
    "paragraph_changes": 1,
    "documents": 2,
    "rules": 1,
    "rules_with_instructions": 1,
    "instructions": 1,
    "rule_sections": 1,
    "matched": 1,
    "shifted": 0,
    "before_history": 0,
    "unmatched": 0,
    "unexplained": 0,
    "citation_self_valid": 1.0,
    "citation_perturbed_rejected": 1.0,
    "parser_precision": 1.0,
    "parser_recall": 1.0,
    "baseline_precision": 0.5,
    "baseline_recall": 1.0,
}


@contextmanager
def _snapshot(parts=None, docs=None, vers=None, xml=None, instruction_map=None):
    parts = PARTS if parts is None else parts
    docs = DOCUMENTS if docs is None else docs
    vers = VERSIONS if vers is None else vers
    xml = DOCUMENT_XML if xml is None else xml
    instruction_map = INSTRUCTION_MAP if instruction_map is None else instruction_map

    def predict(number):
        return instruction_map.get(number, [])

    def fake_verify(section, label, day, quote):
        found = parts[day].sections.get(section)
        text = found.text_of(label) if found is not None else None
        normalized = _normalize(quote)
        if text is not None and normalized in _normalize(text):
            return Verdict("valid")
        return Verdict("not_found")

    with (
        mock.patch.object(experiment, "dates", return_value=sorted(parts)),
        mock.patch.object(experiment, "load_part", side_effect=lambda day: parts[day]),
        mock.patch.object(experiment, "documents", return_value=docs),
        mock.patch.object(experiment, "versions", return_value=vers),
        mock.patch.object(experiment, "document_xml", side_effect=lambda number: xml.get(number)),
        mock.patch.object(experiment, "instructions", side_effect=predict),
        mock.patch.object(experiment, "verify", side_effect=fake_verify),
        mock.patch.object(reconcile_module, "documents", return_value=docs),
        mock.patch.object(reconcile_module, "versions", return_value=vers),
        mock.patch.object(reconcile_module, "instructions", side_effect=predict),
    ):
        yield


class ComputeMetricsTests(unittest.TestCase):
    def test_metrics_match_the_synthetic_snapshot(self) -> None:
        with _snapshot():
            self.assertEqual(experiment.compute_metrics(), EXPECTED)

    def test_repeated_runs_are_identical(self) -> None:
        with _snapshot():
            first = experiment.compute_metrics()
            second = experiment.compute_metrics()
        self.assertEqual(first, second)

    def test_unmatched_rule_leaves_the_change_unexplained(self) -> None:
        vers = [Version("438.2", "2020-01-01", True), Version("438.2", "2021-06-01", True)]
        with _snapshot(vers=vers):
            metrics = experiment.compute_metrics()
        self.assertEqual(metrics["matched"], 0)
        self.assertEqual(metrics["unmatched"], 1)
        self.assertEqual(metrics["unexplained"], 1)
        self.assertEqual(metrics["parser_precision"], 0.0)
        self.assertEqual(metrics["parser_recall"], 0.0)
        self.assertEqual(metrics["baseline_precision"], 0.0)
        self.assertEqual(metrics["baseline_recall"], 0.0)


class HelperTests(unittest.TestCase):
    def test_precision_ignores_before_history_rows(self) -> None:
        rows = [
            Row("2020-0001", "438.2", "matched", "2021-01-01"),
            Row("2020-0001", "438.2", "before_history", None),
            Row("2020-0001", "438.3", "unmatched", None),
        ]
        self.assertEqual(experiment._precision(rows), 0.5)
        self.assertEqual(experiment._precision([]), 0.0)

    def test_recall_counts_unexplained_against_substantive_versions(self) -> None:
        self.assertEqual(experiment._recall([], 4), 1.0)
        self.assertEqual(experiment._recall([("438.2", "2021-01-01")], 4), 0.75)
        self.assertEqual(experiment._recall([], 0), 0.0)

    def test_baseline_predicts_every_438_reference_in_the_xml(self) -> None:
        xml = "<ROOT>See 438.10, 438.2 and 438.68a; 438.2 again.</ROOT>"
        with mock.patch.object(
            experiment, "document_xml", side_effect=lambda number: xml if number == "2020-0001" else None
        ):
            self.assertEqual(experiment._baseline_predict("2020-0001"), ["438.2", "438.10", "438.68a"])
            self.assertEqual(experiment._baseline_predict("2020-0002"), [])


class MainTests(unittest.TestCase):
    def _run(self, path: Path) -> None:
        with mock.patch.object(sys, "argv", ["experiment.py", "--out", str(path)]):
            experiment.main()

    def test_main_writes_sorted_json_without_timestamps(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            with _snapshot():
                self._run(path)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(EXPECTED, indent=2, sort_keys=True) + "\n")

    def test_two_runs_produce_identical_files(self) -> None:
        with TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.json"
            second = Path(tmp) / "second.json"
            with _snapshot():
                self._run(first)
                self._run(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
