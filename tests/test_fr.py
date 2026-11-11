"""Tests for regtrace.fr amendatory instruction parsing."""

from __future__ import annotations

import unittest
from unittest import mock

from regtrace import fr
from regtrace.data import DATA_DIR, documents, section_key
from regtrace.model import Instruction, Version

_VERSIONS = (
    Version("438.2", "2017-01-01", True),
    Version("438.3", "2017-01-01", True),
    Version("438.4", "2017-01-01", True),
    Version("438.6", "2017-01-01", True),
    Version("438.10", "2017-01-01", True),
    Version("438.12", "2017-01-01", True),
)


def _instructions(xml: str | None) -> list[Instruction]:
    with (
        mock.patch.object(fr, "document_xml", return_value=xml),
        mock.patch.object(fr, "versions", return_value=list(_VERSIONS)),
    ):
        return fr.instructions("2024-0001")


def _wrap(*body: str) -> str:
    inner = "".join(body)
    return f'<ROOT><REGTEXT TITLE="42" PART="438">{inner}</REGTEXT></ROOT>'


class InstructionTests(unittest.TestCase):
    def test_numbered_instructions_and_continuations(self) -> None:
        xml = _wrap(
            "<AMDPAR>1. Amend \u00a7 438.2 by revising paragraph (a).</AMDPAR>",
            "<AMDPAR>a. Adding introductory text.</AMDPAR>",
            "<AMDPAR>2. Amend \u00a7 438.10 by removing paragraph (b).</AMDPAR>",
        )
        found = _instructions(xml)
        self.assertEqual([item.number for item in found], [1, 2])
        self.assertEqual(found[0].document, "2024-0001")
        self.assertEqual(
            found[0].text,
            "1. Amend \u00a7 438.2 by revising paragraph (a). a. Adding introductory text.",
        )
        self.assertEqual(found[0].sections, ("438.2",))
        self.assertEqual(found[1].sections, ("438.10",))

    def test_unnumbered_first_instruction_is_zero(self) -> None:
        found = _instructions(_wrap("<AMDPAR>a. Revise \u00a7 438.6.</AMDPAR>"))
        self.assertEqual([item.number for item in found], [0])
        self.assertEqual(found[0].sections, ("438.6",))

    def test_multi_digit_instruction_numbers(self) -> None:
        found = _instructions(
            _wrap(
                "<AMDPAR>9. Amend \u00a7 438.2.</AMDPAR>",
                "<AMDPAR>10. Amend \u00a7 438.4.</AMDPAR>",
            )
        )
        self.assertEqual([item.number for item in found], [9, 10])
        self.assertEqual(found[1].sections, ("438.4",))

    def test_regtext_outside_part_438_is_ignored(self) -> None:
        xml = (
            '<ROOT><REGTEXT TITLE="42" PART="447"><AMDPAR>1. Revise \u00a7 438.2.</AMDPAR></REGTEXT>'
            '<REGTEXT TITLE="42" PART="438"><AMDPAR>2. Revise \u00a7 438.4.</AMDPAR></REGTEXT></ROOT>'
        )
        found = _instructions(xml)
        self.assertEqual([item.number for item in found], [2])
        self.assertEqual(found[0].sections, ("438.4",))

    def test_nested_amdpar_inside_a_division_is_found(self) -> None:
        xml = (
            '<ROOT><REGTEXT TITLE="42" PART="438"><DIV8><AMDPAR>1. Amend \u00a7 438.2.</AMDPAR></DIV8>'
            "</REGTEXT></ROOT>"
        )
        found = _instructions(xml)
        self.assertEqual([item.number for item in found], [1])
        self.assertEqual(found[0].sections, ("438.2",))

    def test_sectno_headings_attach_to_the_current_instruction(self) -> None:
        xml = _wrap(
            "<AMDPAR>3. Revise the following sections:</AMDPAR>",
            "<SECTNO>\u00a7 438.68</SECTNO>",
            "<SECTNO>\u00a7 438.70</SECTNO>",
            "<AMDPAR>4. Amend \u00a7 438.2.</AMDPAR>",
            "<SECTNO>\u00a7 438.2</SECTNO>",
        )
        found = _instructions(xml)
        self.assertEqual([item.number for item in found], [3, 4])
        self.assertEqual(found[0].sections, ("438.68", "438.70"))
        self.assertEqual(found[1].sections, ("438.2",))

    def test_the_current_instruction_carries_across_regtext_blocks(self) -> None:
        xml = (
            '<ROOT><REGTEXT TITLE="42" PART="438">'
            "<AMDPAR>6. Amend \u00a7 438.2 by revising paragraph (a).</AMDPAR></REGTEXT>"
            '<REGTEXT TITLE="42" PART="438">'
            "<AMDPAR>b. Revise paragraph (c) of the following section:</AMDPAR>"
            "<SECTNO>\u00a7 438.10</SECTNO></REGTEXT></ROOT>"
        )
        found = _instructions(xml)
        self.assertEqual([item.number for item in found], [6])
        self.assertEqual(
            found[0].text,
            "6. Amend \u00a7 438.2 by revising paragraph (a). b. Revise paragraph (c) of the following section:",
        )
        self.assertEqual(found[0].sections, ("438.2", "438.10"))

    def test_ranges_expand_against_known_versions(self) -> None:
        found = _instructions(_wrap("<AMDPAR>5. Amend \u00a7\u00a7 438.2 through 438.10.</AMDPAR>"))
        self.assertEqual(found[0].sections, ("438.2", "438.3", "438.4", "438.6", "438.10"))

    def test_sections_are_deduplicated_and_ordered(self) -> None:
        found = _instructions(_wrap("<AMDPAR>6. Amend \u00a7 438.10 and \u00a7438.2 and \u00a7 438.10 again.</AMDPAR>"))
        self.assertEqual(found[0].sections, ("438.2", "438.10"))

    def test_letter_suffix_sections_are_kept(self) -> None:
        found = _instructions(_wrap("<AMDPAR>7. Amend \u00a7 438.68a and \u00a7 438.2.</AMDPAR>"))
        self.assertEqual(found[0].sections, ("438.2", "438.68a"))

    def test_document_without_text_has_no_instructions(self) -> None:
        self.assertEqual(_instructions(None), [])


@unittest.skipUnless((DATA_DIR / "fr").is_dir(), "pinned snapshot not present")
class PinnedInstructionTests(unittest.TestCase):
    def test_unknown_document_has_no_instructions(self) -> None:
        self.assertEqual(fr.instructions("0000-00000"), [])

    def test_pinned_rules_carry_instructions(self) -> None:
        numbers = [document.number for document in documents() if document.has_text][:10]
        self.assertTrue(numbers)
        parsed = [(number, fr.instructions(number)) for number in numbers]
        with_instructions = [(number, items) for number, items in parsed if items]
        self.assertTrue(with_instructions, "no pinned rule has amendatory instructions")
        for number, items in with_instructions:
            self.assertEqual([item.number for item in items], sorted(item.number for item in items))
            for item in items:
                self.assertEqual(item.document, number)
                self.assertEqual(list(item.sections), sorted(item.sections, key=section_key))
                self.assertTrue(item.text)


if __name__ == "__main__":
    unittest.main()
