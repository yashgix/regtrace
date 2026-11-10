"""Tests for the shared value types."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from regtrace.model import (
    Change,
    Document,
    Instruction,
    Paragraph,
    Part,
    Row,
    Section,
    Verdict,
    Version,
)


class ParagraphTests(unittest.TestCase):
    def test_fields_equality_and_hash(self) -> None:
        paragraph = Paragraph("(a)", "Text")
        self.assertEqual(paragraph.label, "(a)")
        self.assertEqual(paragraph.text, "Text")
        self.assertEqual(paragraph, Paragraph("(a)", "Text"))
        self.assertEqual(hash(paragraph), hash(Paragraph("(a)", "Text")))

    def test_frozen(self) -> None:
        paragraph = Paragraph("(a)", "Text")
        with self.assertRaises(FrozenInstanceError):
            paragraph.label = "(b)"


class SectionTests(unittest.TestCase):
    def test_text_of(self) -> None:
        paragraphs = (Paragraph("(a)", "A"), Paragraph("(b)", "B"))
        section = Section("438.2", "\u00a7 438.2 Definitions.", paragraphs)
        self.assertEqual(section.text_of("(a)"), "A")
        self.assertEqual(section.text_of("(b)"), "B")
        self.assertIsNone(section.text_of("(z)"))

    def test_text_of_returns_first_duplicate(self) -> None:
        section = Section("438.2", "", (Paragraph("(a)", "first"), Paragraph("(a)", "second")))
        self.assertEqual(section.text_of("(a)"), "first")

    def test_frozen(self) -> None:
        section = Section("438.2", "Heading", ())
        with self.assertRaises(FrozenInstanceError):
            section.heading = "Changed"


class PartTests(unittest.TestCase):
    def test_sections_keep_insertion_order(self) -> None:
        first = Section("438.2", "Definitions.", ())
        second = Section("438.10", "Other.", ())
        part = Part("2024-01-01", {"438.2": first, "438.10": second})
        self.assertEqual(part.date, "2024-01-01")
        self.assertEqual(list(part.sections), ["438.2", "438.10"])
        self.assertIs(part.sections["438.10"], second)

    def test_frozen(self) -> None:
        part = Part("2024-01-01", {})
        with self.assertRaises(FrozenInstanceError):
            part.date = "2024-01-02"


class ValueObjectTests(unittest.TestCase):
    def test_version(self) -> None:
        version = Version("438.68", "2024-01-01", True)
        self.assertEqual(version.section, "438.68")
        self.assertEqual(version.date, "2024-01-01")
        self.assertTrue(version.substantive)

    def test_document_allows_missing_effective_date(self) -> None:
        document = Document("2024-0001", "Rule", "Final rule", "Title", "2024-01-01", None, True)
        self.assertEqual(document.number, "2024-0001")
        self.assertIsNone(document.effective_on)
        self.assertTrue(document.has_text)

    def test_change_optional_texts(self) -> None:
        revised = Change("438.2", "(a)", "revised", "old", "new")
        removed = Change("438.2", "", "section_removed", None, None)
        self.assertEqual(revised.old_text, "old")
        self.assertEqual(revised.new_text, "new")
        self.assertIsNone(removed.old_text)
        self.assertIsNone(removed.new_text)

    def test_instruction_sections_are_a_tuple(self) -> None:
        instruction = Instruction("2024-0001", 2, "Amend \u00a7 438.2.", ("438.2",))
        self.assertEqual(instruction.number, 2)
        self.assertEqual(instruction.sections, ("438.2",))

    def test_row_allows_missing_date(self) -> None:
        row = Row("2024-0001", "438.2", "unmatched", None)
        self.assertEqual(row.status, "unmatched")
        self.assertIsNone(row.date)

    def test_verdict_defaults_and_payloads(self) -> None:
        valid = Verdict("valid")
        self.assertEqual(valid.status, "valid")
        self.assertIsNone(valid.found_label)
        self.assertEqual(valid.found_dates, ())

        wrong = Verdict("wrong_paragraph", found_label="(b)")
        self.assertEqual(wrong.found_label, "(b)")

        other = Verdict("other_date", found_dates=("2023-01-01", "2024-01-01"))
        self.assertEqual(other.found_dates, ("2023-01-01", "2024-01-01"))


if __name__ == "__main__":
    unittest.main()
