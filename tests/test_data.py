"""Tests for the snapshot loaders in regtrace.data."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from regtrace.data import (
    DATA_DIR,
    dates,
    document_xml,
    documents,
    in_force,
    load_part,
    section_key,
    versions,
)

_SNAPSHOT = """\
<DIV5 xmlns="http://www.w3.org/1999/xhtml">
  <DIV8 N="438.2">
    <HEAD>\u00a7 438.2   Definitions
      and terms.</HEAD>
    <P>(a) First.</P>
    <P>(b) Second.</P>
  </DIV8>
  <DIV8 N="438.10">
    <HEAD>\u00a7 438.10 Information requirements.</HEAD>
    <P>(a) One.</P>
  </DIV8>
  <DIV8>
    <HEAD>Untitled.</HEAD>
  </DIV8>
</DIV5>
"""

_VERSIONS = {
    "content_versions": [
        {"identifier": "438.2", "date": "2020-01-01", "substantive": True},
        {"identifier": "438.2", "date": "2021-01-01", "substantive": False},
    ],
}

_DOCUMENTS = {
    "results": [
        {
            "document_number": "2020-0001",
            "type": "Rule",
            "action": "Final rule",
            "title": "Managed care",
            "publication_date": "2020-01-01",
            "effective_on": "2020-03-01",
        },
        {
            "document_number": "2020-0002",
            "type": "Proposed Rule",
            "action": "Proposed rule",
            "title": "Managed care",
            "publication_date": "2020-02-01",
            "effective_on": None,
        },
    ],
}


class SectionKeyTests(unittest.TestCase):
    def test_numeric_order(self) -> None:
        self.assertEqual(sorted(["438.100", "438.2", "438.10"], key=section_key), ["438.2", "438.10", "438.100"])

    def test_letter_suffix_follows_number(self) -> None:
        self.assertLess(section_key("438.68"), section_key("438.68a"))
        self.assertLess(section_key("438.68a"), section_key("438.69"))

    def test_unparseable_ids_sort_last(self) -> None:
        ordered = sorted(["438", "Part 438", "438.2"], key=section_key)
        self.assertEqual(ordered[0], "438.2")
        self.assertEqual(ordered[-1], "Part 438")


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        (self.data_dir / "ecfr").mkdir()
        (self.data_dir / "fr").mkdir()
        for day in ("2020-01-01", "2021-01-01"):
            (self.data_dir / "ecfr" / f"part438-{day}.xml").write_text(_SNAPSHOT, encoding="utf-8")
        (self.data_dir / "ecfr" / "versions.json").write_text(json.dumps(_VERSIONS), encoding="utf-8")
        (self.data_dir / "fr" / "documents.json").write_text(json.dumps(_DOCUMENTS), encoding="utf-8")
        (self.data_dir / "fr" / "2020-0001.xml").write_text("<ROOT/>", encoding="utf-8")

    def test_dates_are_sorted_and_ignore_foreign_names(self) -> None:
        (self.data_dir / "ecfr" / "part438-not-a-date.xml").write_text(_SNAPSHOT, encoding="utf-8")
        self.assertEqual(dates(self.data_dir), ["2020-01-01", "2021-01-01"])

    def test_load_part_normalizes_headings_and_labels(self) -> None:
        part = load_part("2020-01-01", self.data_dir)
        self.assertEqual(part.date, "2020-01-01")
        self.assertEqual(list(part.sections), ["438.2", "438.10"])
        section = part.sections["438.2"]
        self.assertEqual(section.heading, "\u00a7 438.2 Definitions and terms.")
        self.assertEqual([paragraph.label for paragraph in section.paragraphs], ["(a)", "(b)"])
        self.assertEqual(section.text_of("(b)"), "(b) Second.")

    def test_load_part_rejects_unknown_dates(self) -> None:
        with self.assertRaises(KeyError):
            load_part("1999-01-01", self.data_dir)

    def test_in_force_boundaries(self) -> None:
        self.assertIsNone(in_force("2019-12-31", self.data_dir))
        self.assertEqual(in_force("2020-01-01", self.data_dir), "2020-01-01")
        self.assertEqual(in_force("2020-12-31", self.data_dir), "2020-01-01")
        self.assertEqual(in_force("2021-01-01", self.data_dir), "2021-01-01")
        self.assertEqual(in_force("2030-01-01", self.data_dir), "2021-01-01")

    def test_versions_carry_flags(self) -> None:
        found = versions(self.data_dir)
        self.assertEqual([version.date for version in found], ["2020-01-01", "2021-01-01"])
        self.assertEqual([version.section for version in found], ["438.2", "438.2"])
        self.assertEqual([version.substantive for version in found], [True, False])

    def test_documents_keep_file_order_and_text_flag(self) -> None:
        found = documents(self.data_dir)
        self.assertEqual([document.number for document in found], ["2020-0001", "2020-0002"])
        self.assertEqual(found[0].effective_on, "2020-03-01")
        self.assertIsNone(found[1].effective_on)
        self.assertTrue(found[0].has_text)
        self.assertFalse(found[1].has_text)
        self.assertEqual(found[1].type, "Proposed Rule")

    def test_document_xml(self) -> None:
        self.assertEqual(document_xml("2020-0001", self.data_dir), "<ROOT/>")
        self.assertIsNone(document_xml("2020-0002", self.data_dir))


@unittest.skipUnless((DATA_DIR / "ecfr").is_dir(), "pinned snapshot not present")
class PinnedSnapshotTests(unittest.TestCase):
    def test_dates(self) -> None:
        found = dates()
        self.assertEqual(len(found), 38)
        self.assertEqual(len(set(found)), 38)
        self.assertEqual(found, sorted(found))
        self.assertEqual(found[0], "2017-01-01")
        self.assertEqual(found[-1], "2026-07-31")
        for day in found:
            self.assertEqual(date.fromisoformat(day).isoformat(), day)

    def test_latest_part_parses(self) -> None:
        part = load_part(dates()[-1])
        self.assertTrue(part.sections)
        heading = part.sections["438.2"].heading
        self.assertTrue(heading.startswith("\u00a7 438.2 "))
        self.assertEqual(heading, " ".join(heading.split()))
        self.assertTrue(part.sections["438.2"].paragraphs)

    def test_in_force_against_pinned_dates(self) -> None:
        self.assertIsNone(in_force("2016-12-31"))
        self.assertEqual(in_force("2017-01-01"), "2017-01-01")
        self.assertEqual(in_force("2017-01-02"), "2017-01-01")
        self.assertEqual(in_force("2030-01-01"), dates()[-1])

    def test_documents_and_rules(self) -> None:
        found = documents()
        self.assertEqual(len(found), 45)
        self.assertEqual(sum(1 for document in found if document.type == "Rule"), 26)
        days = [document.publication_date for document in found]
        self.assertEqual(days, sorted(days))
        for document in found:
            self.assertEqual(document.has_text, (DATA_DIR / "fr" / f"{document.number}.xml").is_file())

    def test_versions_and_document_xml(self) -> None:
        self.assertTrue(versions())
        self.assertIsNone(document_xml("0000-00000"))
        with_text = next(document for document in documents() if document.has_text)
        text = document_xml(with_text.number)
        self.assertIsNotNone(text)
        self.assertTrue(text.startswith("<"))


if __name__ == "__main__":
    unittest.main()
