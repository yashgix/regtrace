"""Tests for the evidence rendering in demo.py."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import demo
from regtrace.model import Change, Document, Paragraph, Part, Row, Section, Verdict

DASH = "—"


def _section(section_id: str, *paragraphs: tuple[str, str], heading: str | None = None) -> Section:
    title = heading or f"§ {section_id} Heading."
    return Section(section_id, title, tuple(Paragraph(label, text) for label, text in paragraphs))


def _part(day: str, *sections: Section) -> Part:
    return Part(day, {section.id: section for section in sections})


class TextTests(unittest.TestCase):
    def test_normalize_collapses_whitespace(self) -> None:
        self.assertEqual(demo._normalize("  a\n b\t c "), "a b c")

    def test_short_leaves_short_text_alone(self) -> None:
        self.assertEqual(demo._short("short"), "short")

    def test_short_truncates_and_marks_the_cut(self) -> None:
        short = demo._short("word " * 40, limit=20)
        self.assertLessEqual(len(short), 20)
        self.assertTrue(short.endswith("…"))
        self.assertFalse(short.endswith(" …"))

    def test_cell_normalizes_none_and_escapes_pipes(self) -> None:
        self.assertEqual(demo._cell(None), "")
        self.assertEqual(demo._cell("  a | b\n"), "a \\| b")


class TableTests(unittest.TestCase):
    def test_table_has_a_header_a_rule_and_escaped_cells(self) -> None:
        text = demo._table(("a", "b"), [("x|y", None)])
        self.assertEqual(text.splitlines(), ["| a | b |", "|---|---|", "| x\\|y |  |"])

    def test_metrics_table_sorts_metric_names(self) -> None:
        text = demo._metrics_table({"matched": 2, "dates": 1})
        self.assertTrue(text.startswith("### Metrics\n\n"))
        self.assertLess(text.index("| dates | 1 |"), text.index("| matched | 2 |"))


class UnexplainedTableTests(unittest.TestCase):
    def test_empty_list_renders_none(self) -> None:
        self.assertEqual(demo._unexplained_table([]), "### Unexplained changes\n\n_None._")

    def test_row_carries_heading_and_next_check(self) -> None:
        part = _part("2021-01-01", _section("438.2", ("(a)", "(a) Text."), heading="§ 438.2 Network | adequacy."))
        with mock.patch.object(demo, "load_part", return_value=part):
            text = demo._unexplained_table([("438.2", "2021-01-01")])
        self.assertIn("| 438.2 | 2021-01-01 | § 438.2 Network \\| adequacy. |", text)
        self.assertIn("Check Federal Register documents around 2021-01-01 for an untagged § 438.2 amendment.", text)

    def test_missing_section_renders_an_empty_heading(self) -> None:
        part = _part("2021-01-01", _section("438.2"))
        with mock.patch.object(demo, "load_part", return_value=part):
            text = demo._unexplained_table([("438.99", "2021-01-01")])
        self.assertIn("| 438.99 | 2021-01-01 |  |", text)


class DiscrepancyTableTests(unittest.TestCase):
    DOCUMENTS = [
        Document("2020-0001", "Rule", "Final rule", "Title", "2020-06-01", "2021-01-01", True),
        Document("2020-0002", "Rule", "Final rule", "Title", "2020-07-01", None, True),
    ]

    def test_empty_rows_render_none(self) -> None:
        with mock.patch.object(demo, "documents", return_value=self.DOCUMENTS):
            self.assertEqual(demo._discrepancy_table([]), "### Discrepancies\n\n_None._")

    def test_only_shifted_and_unmatched_rows_are_listed(self) -> None:
        rows = [
            Row("2020-0001", "438.2", "matched", "2021-01-01"),
            Row("2020-0001", "438.10", "shifted", "2021-02-01"),
            Row("2020-0002", "438.68", "unmatched", None),
            Row("2020-0002", "438.70", "before_history", None),
        ]
        with mock.patch.object(demo, "documents", return_value=self.DOCUMENTS):
            text = demo._discrepancy_table(rows)
        self.assertIn("| 2020-0001 | 438.10 | 2021-01-01 | 2021-02-01 | shifted |", text)
        self.assertIn(f"| 2020-0002 | 438.68 | 2020-07-01 | {DASH} | unmatched |", text)
        self.assertNotIn("| matched |", text)
        self.assertNotIn("before_history", text)


class WalkthroughTests(unittest.TestCase):
    def test_walkthrough_shows_snapshot_changes_and_citation_check(self) -> None:
        early = _part("2020-01-01", _section("438.68", ("(a)", "(a) Old text about network adequacy standards.")))
        latest = _part(
            "2021-01-01",
            _section(
                "438.68",
                ("(a)", "(a) New text about network adequacy standards."),
                ("(b)", "(b) Another paragraph long enough to quote."),
            ),
        )
        parts = {"2020-01-01": early, "2021-01-01": latest}
        with (
            mock.patch.object(demo, "dates", return_value=["2020-01-01", "2021-01-01"]),
            mock.patch.object(demo, "load_part", side_effect=lambda day: parts[day]),
            mock.patch.object(demo, "diff", return_value=[Change("438.68", "(a)", "revised", "old", "new")]),
            mock.patch.object(demo, "verify", side_effect=[Verdict("valid"), Verdict("not_found")]),
        ):
            text = demo._walkthrough()
        self.assertIn("Latest eCFR snapshot: `2021-01-01` with 1 sections.", text)
        self.assertIn("**§ 438.68 Heading.**", text)
        self.assertIn("- `(a)` (a) New text about network adequacy standards.", text)
        self.assertIn("Changes from `2020-01-01` to `2021-01-01`: 1.", text)
        self.assertIn("- `revised` 438.68 (a)", text)
        self.assertIn("Citation check on `438.68(a)`: `valid`; with the last word replaced: `not_found`.", text)

    def test_walkthrough_without_sections(self) -> None:
        with (
            mock.patch.object(demo, "dates", return_value=["2021-01-01"]),
            mock.patch.object(demo, "load_part", return_value=Part("2021-01-01", {})),
        ):
            self.assertEqual(demo._walkthrough(), "### Walk-through\n\n_The latest snapshot has no sections._")


class RenderTests(unittest.TestCase):
    def test_render_joins_the_four_blocks_in_order(self) -> None:
        with (
            mock.patch.object(demo, "reconcile", return_value=([], [])),
            mock.patch.object(demo, "documents", return_value=[]),
            mock.patch.object(demo, "_walkthrough", return_value="### Walk-through\n\nText."),
        ):
            text = demo.render({"matched": 1, "dates": 2})
            again = demo.render({"matched": 1, "dates": 2})
        self.assertEqual(text, again)
        self.assertTrue(text.startswith("### Metrics"))
        self.assertIn("| dates | 2 |", text)
        self.assertIn("### Unexplained changes\n\n_None._", text)
        self.assertIn("### Discrepancies\n\n_None._", text)
        self.assertLess(text.index("### Metrics"), text.index("### Unexplained changes"))
        self.assertLess(text.index("### Unexplained changes"), text.index("### Discrepancies"))
        self.assertLess(text.index("### Discrepancies"), text.index("### Walk-through"))
        self.assertTrue(text.endswith("Text.\n"))


class ReadmeTests(unittest.TestCase):
    def test_render_readme_replaces_only_the_block(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                f"Intro.\n\n{demo.EVIDENCE_START}\n\nold\n\n{demo.EVIDENCE_END}\n\nTail.\n",
                encoding="utf-8",
            )
            with mock.patch.object(demo, "render", return_value="NEW\n"):
                text = demo.render_readme({"dates": 2}, readme)
        self.assertEqual(text, f"Intro.\n\n{demo.EVIDENCE_START}\n\nNEW\n\n{demo.EVIDENCE_END}\n\nTail.\n")

    def test_render_readme_without_markers_exits(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text("No markers here.\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                demo.render_readme({"dates": 2}, readme)

    def test_render_readme_without_a_closing_marker_exits(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            original = f"Intro.\n\n{demo.EVIDENCE_START}\n\nold\n\nTail.\n"
            readme.write_text(original, encoding="utf-8")
            with mock.patch.object(demo, "render", return_value="NEW\n"), self.assertRaises(SystemExit):
                demo.render_readme({"dates": 2}, readme)
            self.assertEqual(readme.read_text(encoding="utf-8"), original)

    def test_render_readme_with_two_closing_markers_exits(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            original = f"Intro.\n\n{demo.EVIDENCE_START}\n\nold\n\n{demo.EVIDENCE_END}\n\n{demo.EVIDENCE_END}\n\nTail.\n"
            readme.write_text(original, encoding="utf-8")
            with mock.patch.object(demo, "render", return_value="NEW\n"), self.assertRaises(SystemExit):
                demo.render_readme({"dates": 2}, readme)
            self.assertEqual(readme.read_text(encoding="utf-8"), original)


class LoadMetricsTests(unittest.TestCase):
    def test_load_metrics_reads_json(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            path.write_text(json.dumps({"dates": 2, "matched": 1}), encoding="utf-8")
            self.assertEqual(demo._load_metrics(path), {"dates": 2, "matched": 1})

    def test_load_metrics_falls_back_to_compute_metrics(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "metrics.json"
            with mock.patch("experiment.compute_metrics", return_value={"dates": 2}):
                self.assertEqual(demo._load_metrics(missing), {"dates": 2})

    def test_load_metrics_required_with_missing_file_exits(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "metrics.json"
            with self.assertRaises(SystemExit):
                demo._load_metrics(missing, required=True)


class MainTests(unittest.TestCase):
    def test_main_writes_the_rendered_evidence_to_out(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "evidence.md"
            with (
                mock.patch.object(demo, "_load_metrics", return_value={"dates": 2}),
                mock.patch.object(demo, "render", return_value="TEXT\n"),
                mock.patch.object(sys, "argv", ["demo.py", "--out", str(out)]),
            ):
                demo.main()
            self.assertEqual(out.read_text(encoding="utf-8"), "TEXT\n")

    def test_main_prints_to_stdout_by_default(self) -> None:
        buffer = io.StringIO()
        with (
            mock.patch.object(demo, "_load_metrics", return_value={"dates": 2}),
            mock.patch.object(demo, "render", return_value="TEXT\n"),
            mock.patch.object(sys, "argv", ["demo.py"]),
            redirect_stdout(buffer),
        ):
            demo.main()
        self.assertEqual(buffer.getvalue(), "TEXT\n")

    def test_main_refreshes_the_readme(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text("old", encoding="utf-8")
            with (
                mock.patch.object(demo, "_load_metrics", return_value={"dates": 2}),
                mock.patch.object(demo, "render_readme", return_value="fresh"),
                mock.patch.object(sys, "argv", ["demo.py", "--readme", str(readme)]),
            ):
                demo.main()
            self.assertEqual(readme.read_text(encoding="utf-8"), "fresh")

    def test_main_does_not_touch_readme_when_metrics_file_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            original = f"Intro.\n\n{demo.EVIDENCE_START}\n\nold\n\n{demo.EVIDENCE_END}\n\nTail.\n"
            readme.write_text(original, encoding="utf-8")
            missing = Path(tmp) / "missing" / "metrics.json"
            with (
                mock.patch.object(sys, "argv", ["demo.py", "--metrics", str(missing), "--readme", str(readme)]),
                self.assertRaises(SystemExit),
            ):
                demo.main()
            self.assertEqual(readme.read_text(encoding="utf-8"), original)

    def test_main_leaves_the_readme_alone_when_a_marker_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            original = f"Intro.\n\n{demo.EVIDENCE_START}\n\nold\n\nTail.\n"
            readme.write_text(original, encoding="utf-8")
            with (
                mock.patch.object(demo, "_load_metrics", return_value={"dates": 2}),
                mock.patch.object(demo, "render", return_value="NEW\n"),
                mock.patch.object(sys, "argv", ["demo.py", "--readme", str(readme)]),
                self.assertRaises(SystemExit),
            ):
                demo.main()
            self.assertEqual(readme.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
