'''Tests for regtrace.diff.'''

from __future__ import annotations

import unittest

from regtrace.data import DATA_DIR, dates, load_part, section_key
from regtrace.diff import changes_between, diff
from regtrace.model import Change, Paragraph, Part, Section


def _section(section_id: str, heading: str, *paragraphs: tuple[str, str]) -> Section:
    return Section(section_id, heading, tuple(Paragraph(label, text) for label, text in paragraphs))


class DiffTests(unittest.TestCase):
    def test_identical_parts_have_no_changes(self) -> None:
        part = Part("2020-01-01", {"438.2": _section("438.2", "Heading.", ("(a)", "A"))})
        self.assertEqual(diff(part, part), [])

    def test_section_added_and_removed(self) -> None:
        old = Part("2020-01-01", {"438.2": _section("438.2", "Old heading.", ("(a)", "A"))})
        new = Part("2021-01-01", {"438.68": _section("438.68", "New heading.", ("(a)", "A"))})
        self.assertEqual(
            diff(old, new),
            [
                Change("438.2", "", "section_removed", None, None),
                Change("438.68", "", "section_added", None, None),
            ],
        )

    def test_heading_paragraph_order_and_kinds(self) -> None:
        old = Part(
            "2020-01-01",
            {"438.2": _section("438.2", "\u00a7 438.2 Definitions.", ("(a)", "A"), ("(b)", "B"), ("(c)", "C"))},
        )
        new = Part(
            "2021-01-01",
            {
                "438.2": _section(
                    "438.2",
                    "\u00a7 438.2 Definitions and terms.",
                    ("(a)", "A"),
                    ("(b)", "B2"),
                    ("(d)", "D"),
                )
            },
        )
        self.assertEqual(
            diff(old, new),
            [
                Change("438.2", "", "heading_revised", "\u00a7 438.2 Definitions.", "\u00a7 438.2 Definitions and terms."),
                Change("438.2", "(b)", "revised", "B", "B2"),
                Change("438.2", "(d)", "added", None, "D"),
                Change("438.2", "(c)", "removed", "C", None),
            ],
        )

    def test_sections_are_visited_in_section_key_order(self) -> None:
        old = Part(
            "2020-01-01",
            {
                "438.10": _section("438.10", "Ten.", ("(a)", "A")),
                "438.2": _section("438.2", "Two.", ("(a)", "A")),
            },
        )
        new = Part("2021-01-01", {})
        self.assertEqual([change.section for change in diff(old, new)], ["438.2", "438.10"])


@unittest.skipUnless((DATA_DIR / "ecfr").is_dir(), "pinned snapshot not present")
class PinnedDiffTests(unittest.TestCase):
    def test_self_diff_is_empty(self) -> None:
        part = load_part(dates()[0])
        self.assertEqual(diff(part, part), [])

    def test_oldest_and_newest_snapshots_differ(self) -> None:
        all_dates = dates()
        old_part = load_part(all_dates[0])
        new_part = load_part(all_dates[-1])
        changes = changes_between(all_dates[0], all_dates[-1])
        self.assertTrue(changes)
        known = set(old_part.sections) | set(new_part.sections)
        for change in changes:
            self.assertIn(change.section, known)

    def test_real_changes_are_ordered(self) -> None:
        all_dates = dates()
        changes = changes_between(all_dates[0], all_dates[-1])
        keys = [section_key(change.section) for change in changes]
        self.assertEqual(keys, sorted(keys))


if __name__ == "__main__":
    unittest.main()
