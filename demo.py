"""Render the evidence tables and a short walk-through of the library."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from regtrace.cite import verify
from regtrace.data import dates, documents, load_part
from regtrace.diff import diff
from regtrace.model import Paragraph, Part, Row, Section
from regtrace.reconcile import reconcile

EVIDENCE_START = "<!-- regtrace:evidence:start -->"
EVIDENCE_END = "<!-- regtrace:evidence:end -->"
METRICS_PATH = Path("results/metrics.json")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _short(text: str, limit: int = 90) -> str:
    text = _normalize(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    return _normalize(text).replace("|", "\\|")


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _metrics_table(metrics: dict[str, int | float]) -> str:
    rows = [(key, metrics[key]) for key in sorted(metrics)]
    return "### Metrics\n\n" + _table(("metric", "value"), rows)


def _unexplained_table(unexplained: list[tuple[str, str]]) -> str:
    if not unexplained:
        return "### Unexplained changes\n\n_None._"
    parts = {day: load_part(day) for _, day in unexplained}
    rows = []
    for section_id, day in unexplained:
        section = parts[day].sections.get(section_id)
        heading = section.heading if section is not None else ""
        next_check = f"Check Federal Register documents around {day} for an untagged § {section_id} amendment."
        rows.append((section_id, day, _short(heading, 80), next_check))
    return "### Unexplained changes\n\n" + _table(("section", "date", "heading", "next check"), rows)


def _discrepancy_table(rows: list[Row]) -> str:
    by_number = {document.number: document for document in documents()}
    discrepancies = []
    for row in rows:
        if row.status not in {"shifted", "unmatched"}:
            continue
        document = by_number[row.document]
        expected = document.effective_on or document.publication_date
        discrepancies.append((row.document, row.section, expected, row.date or "—", row.status))
    if not discrepancies:
        return "### Discrepancies\n\n_None._"
    return "### Discrepancies\n\n" + _table(
        ("document", "section", "expected", "eCFR date", "status"),
        discrepancies,
    )


def _first_quote(part: Part) -> tuple[Section, Paragraph, str] | None:
    for section in part.sections.values():
        for paragraph in section.paragraphs:
            quote = _normalize(paragraph.text)
            if len(quote) >= 20:
                return section, paragraph, quote
    return None


def _walkthrough() -> str:
    all_dates = dates()
    latest = all_dates[-1]
    part = load_part(latest)
    if not part.sections:
        return "### Walk-through\n\n_The latest snapshot has no sections._"
    section = part.sections.get("438.68") or next(iter(part.sections.values()))
    lines = [
        "### Walk-through",
        "",
        f"Latest eCFR snapshot: `{latest}` with {len(part.sections)} sections.",
        "",
        f"**{section.heading}**",
    ]
    for paragraph in section.paragraphs[:3]:
        lines.append(f"- `{paragraph.label}` {_short(paragraph.text, 160)}")
    if len(all_dates) >= 2:
        previous = all_dates[-2]
        changes = diff(load_part(previous), part)
        lines += ["", f"Changes from `{previous}` to `{latest}`: {len(changes)}."]
        for change in changes[:5]:
            label = change.label or "heading"
            lines.append(f"- `{change.kind}` {change.section} {label}")
    choice = _first_quote(part)
    if choice is not None:
        chosen_section, paragraph, quote = choice
        verdict = verify(chosen_section.id, paragraph.label, latest, quote)
        perturbed = re.sub(r"\S+$", "zzzz", quote)
        rejected = verify(chosen_section.id, paragraph.label, latest, perturbed)
        lines += [
            "",
            f"Citation check on `{chosen_section.id}{paragraph.label}`: "
            f"`{verdict.status}`; with the last word replaced: `{rejected.status}`.",
        ]
    return "\n".join(lines)


def render(metrics: dict[str, int | float]) -> str:
    """Return the evidence block: metrics, unexplained changes, discrepancies, walk-through."""
    rows, unexplained = reconcile()
    blocks = [
        _metrics_table(metrics),
        _unexplained_table(unexplained),
        _discrepancy_table(rows),
        _walkthrough(),
    ]
    return "\n\n".join(blocks) + "\n"


def render_readme(metrics: dict[str, int | float], readme: Path) -> str:
    """Return the README with its generated evidence block refreshed."""
    text = readme.read_text(encoding="utf-8")
    head, marker, rest = text.partition(EVIDENCE_START)
    if not marker:
        raise SystemExit(f"{readme} has no {EVIDENCE_START} ... {EVIDENCE_END} block")
    _, end_marker, tail = rest.partition(EVIDENCE_END)
    if not end_marker or EVIDENCE_END in tail:
        raise SystemExit(f"{readme} must have exactly one {EVIDENCE_END} after {EVIDENCE_START}")
    return f"{head}{EVIDENCE_START}\n\n{render(metrics).rstrip()}\n\n{EVIDENCE_END}{tail}"


def _load_metrics(path: Path, *, required: bool = False) -> dict[str, int | float]:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    if required:
        raise SystemExit(f"{path} not found; run `python experiment.py --out {path}` first")
    try:
        from experiment import compute_metrics
    except ImportError as exc:
        raise SystemExit(f"{path} not found; run `python experiment.py --out {path}` first") from exc
    return compute_metrics()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=METRICS_PATH)
    parser.add_argument("--out", type=Path, help="write the output here (with --readme: the whole rendered README)")
    parser.add_argument("--readme", type=Path, help="render the generated block of this README (in place without --out)")
    args = parser.parse_args()

    metrics = _load_metrics(args.metrics, required=args.readme is not None)
    if args.readme is not None:
        # Render before writing so a malformed README is never touched.
        rendered = render_readme(metrics, args.readme)
        target = args.out or args.readme
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        return

    text = render(metrics)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
