"""Tests for regtrace.cite.verify status precedence and payloads."""

from __future__ import annotations

import unittest
from unittest import mock

import regtrace.cite as cite_module
from regtrace.model import Paragraph, Part, Section, Verdict

QUOTE = "Providers must meet the network adequacy standards"


def _section(section_id: str, *paragraphs: tuple[str, str]) -> Section:
    return Section(
        section_id,
        f"§ {section_id} Heading.",
        tuple(Paragraph(label, text) for label, text in paragraphs),
    )


def _part(day: str, *sections: Section) -> Part:
    return Part(day, {section.id: section for section in sections})


def _verify(
    parts: dict[str, Part],
    effective: str | None,
    all_dates: list[str],
    section: str = "438.2",
    label: str = "(a)",
    date: str = "2021-01-01",
    quote: str = QUOTE,
) -> Verdict:
    with (
        mock.patch.object(cite_module, "in_force", return_value=effective),
        mock.patch.object(cite_module, "load_part", side_effect=lambda day: parts[day]),
        mock.patch.object(cite_module, "dates", return_value=all_dates),
    ):
        return cite_module.verify(section, label, date, quote)


class VerifyTests(unittest.TestCase):
    def test_too_short_quote_short_circuits_before_data_lookup(self) -> None:
        with mock.patch.object(cite_module, "in_force", side_effect=AssertionError("called")):
            verdict = cite_module.verify("438.2", "(a)", "2021-01-01", "short")
        self.assertEqual(verdict, Verdict("too_short"))

    def test_twenty_characters_is_long_enough_to_reach_data_lookup(self) -> None:
        with mock.patch.object(cite_module, "in_force", return_value=None):
            verdict = cite_module.verify("438.2", "(a)", "2021-01-01", "12345678901234567890")
        self.assertEqual(verdict, Verdict("no_data"))

    def test_no_data_when_date_precedes_history(self) -> None:
        with mock.patch.object(cite_module, "in_force", return_value=None):
            verdict = cite_module.verify("438.2", "(a)", "2016-12-31", QUOTE)
        self.assertEqual(verdict, Verdict("no_data"))

    def test_valid_normalizes_whitespace(self) -> None:
        section = _section("438.2", ("(a)", f"(a) {QUOTE}."))
        parts = {"2021-01-01": _part("2021-01-01", section)}
        verdict = _verify(
            parts,
            "2021-01-01",
            ["2021-01-01"],
            quote="Providers   must\nmeet the network adequacy standards",
        )
        self.assertEqual(verdict, Verdict("valid"))

    def test_valid_accepts_a_substring_of_the_paragraph(self) -> None:
        section = _section("438.2", ("(a)", f"(a) Introductory text. {QUOTE} in this section."))
        parts = {"2021-01-01": _part("2021-01-01", section)}
        verdict = _verify(parts, "2021-01-01", ["2021-01-01"])
        self.assertEqual(verdict, Verdict("valid"))

    def test_wrong_paragraph_returns_first_matching_label(self) -> None:
        section = _section(
            "438.2",
            ("(a)", "(a) Something else entirely."),
            ("(b)", f"(b) {QUOTE} in this paragraph."),
            ("(c)", f"(c) {QUOTE} again in a later paragraph."),
        )
        parts = {"2021-01-01": _part("2021-01-01", section)}
        verdict = _verify(parts, "2021-01-01", ["2021-01-01"], label="(a)")
        self.assertEqual(verdict, Verdict("wrong_paragraph", found_label="(b)"))

    def test_wrong_paragraph_beats_other_date(self) -> None:
        effective_section = _section(
            "438.2",
            ("(a)", "(a) Different text at the effective date."),
            ("(b)", f"(b) {QUOTE} appears here."),
        )
        old_section = _section("438.2", ("(a)", f"(a) {QUOTE} at the old date."))
        parts = {
            "2020-01-01": _part("2020-01-01", old_section),
            "2021-01-01": _part("2021-01-01", effective_section),
        }
        verdict = _verify(parts, "2021-01-01", ["2020-01-01", "2021-01-01"], label="(a)")
        self.assertEqual(verdict, Verdict("wrong_paragraph", found_label="(b)"))

    def test_other_date_returns_all_dates_ascending(self) -> None:
        effective_section = _section("438.2", ("(a)", "(a) Current text without the quote."))
        old_section = _section("438.2", ("(a)", f"(a) {QUOTE} at the old date."))
        older_section = _section("438.2", ("(a)", f"(a) {QUOTE} at the older date."))
        parts = {
            "2019-01-01": _part("2019-01-01", older_section),
            "2020-01-01": _part("2020-01-01", old_section),
            "2021-01-01": _part("2021-01-01", effective_section),
        }
        verdict = _verify(
            parts,
            "2021-01-01",
            ["2019-01-01", "2020-01-01", "2021-01-01"],
            label="(a)",
        )
        self.assertEqual(verdict, Verdict("other_date", found_dates=("2019-01-01", "2020-01-01")))

    def test_section_missing_at_effective_date_can_be_found_at_another_date(self) -> None:
        old_section = _section("438.2", ("(a)", f"(a) {QUOTE} at the old date."))
        other_section = _section("438.10", ("(a)", "(a) Other section."))
        parts = {
            "2020-01-01": _part("2020-01-01", old_section),
            "2021-01-01": _part("2021-01-01", other_section),
        }
        verdict = _verify(parts, "2021-01-01", ["2020-01-01", "2021-01-01"])
        self.assertEqual(verdict, Verdict("other_date", found_dates=("2020-01-01",)))

    def test_not_found(self) -> None:
        section = _section("438.2", ("(a)", "(a) Current text."))
        parts = {"2021-01-01": _part("2021-01-01", section)}
        verdict = _verify(parts, "2021-01-01", ["2021-01-01"])
        self.assertEqual(verdict, Verdict("not_found"))

    def test_other_date_only_matches_the_same_label(self) -> None:
        effective_section = _section("438.2", ("(a)", "(a) Current text without the quote."))
        old_section = _section("438.2", ("(b)", f"(b) {QUOTE} under another label."))
        parts = {
            "2020-01-01": _part("2020-01-01", old_section),
            "2021-01-01": _part("2021-01-01", effective_section),
        }
        verdict = _verify(parts, "2021-01-01", ["2020-01-01", "2021-01-01"], label="(a)")
        self.assertEqual(verdict, Verdict("not_found"))


if __name__ == "__main__":
    unittest.main()
