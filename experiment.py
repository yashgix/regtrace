"""Compute the deterministic metrics used by the README."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from regtrace.cite import verify
from regtrace.data import dates, document_xml, documents, load_part, section_key, versions
from regtrace.diff import diff
from regtrace.fr import instructions
from regtrace.model import Part, Row
from regtrace.reconcile import reconcile


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _share(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _citation_metrics(latest: str, part: Part) -> tuple[float, float]:
    total = 0
    valid = 0
    rejected = 0
    for section in part.sections.values():
        for paragraph in section.paragraphs:
            quote = _normalize(paragraph.text)
            if len(quote) < 20:
                continue
            total += 1
            if verify(section.id, paragraph.label, latest, quote).status == "valid":
                valid += 1
            perturbed = re.sub(r"\S+$", "zzzz", quote)
            if verify(section.id, paragraph.label, latest, perturbed).status != "valid":
                rejected += 1
    return _share(valid, total), _share(rejected, total)


def _precision(rows: list[Row]) -> float:
    counts = Counter(row.status for row in rows)
    considered = len(rows) - counts["before_history"]
    return _share(counts["matched"] + counts["shifted"], considered)


def _recall(unexplained: list[tuple[str, str]], substantive: int) -> float:
    return round(1 - len(unexplained) / substantive, 6) if substantive else 0.0


def _baseline_predict(number: str) -> list[str]:
    xml = document_xml(number)
    if xml is None:
        return []
    found = {f"438.{match}" for match in re.findall(r"438\.(\d+[a-z]?)", xml)}
    return sorted(found, key=section_key)


def compute_metrics() -> dict[str, int | float]:
    all_dates = dates()
    latest = all_dates[-1]
    latest_part = load_part(latest)
    paragraphs = [paragraph for section in latest_part.sections.values() for paragraph in section.paragraphs]

    docs = documents()
    rules = [document for document in docs if document.type == "Rule"]
    rule_instructions = {document.number: instructions(document.number) for document in rules}

    rows, unexplained = reconcile()
    status_counts = Counter(row.status for row in rows)
    all_versions = versions()
    base = min(version.date for version in all_versions)
    substantive = sum(1 for version in all_versions if version.substantive and version.date != base)

    self_valid, perturbed_rejected = _citation_metrics(latest, latest_part)
    baseline_rows, baseline_unexplained = reconcile(predict=_baseline_predict)
    paragraph_changes = sum(
        len(diff(load_part(left), load_part(right)))
        for left, right in zip(all_dates, all_dates[1:], strict=False)
    )

    return {
        "dates": len(all_dates),
        "sections_latest": len(latest_part.sections),
        "paragraphs_latest": len(paragraphs),
        "unlabeled_latest": sum(1 for paragraph in paragraphs if "~" in paragraph.label),
        "paragraph_changes": paragraph_changes,
        "documents": len(docs),
        "rules": len(rules),
        "rules_with_instructions": sum(1 for items in rule_instructions.values() if items),
        "instructions": sum(len(items) for items in rule_instructions.values()),
        "rule_sections": len(rows),
        "matched": status_counts["matched"],
        "shifted": status_counts["shifted"],
        "before_history": status_counts["before_history"],
        "unmatched": status_counts["unmatched"],
        "unexplained": len(unexplained),
        "citation_self_valid": self_valid,
        "citation_perturbed_rejected": perturbed_rejected,
        "parser_precision": _precision(rows),
        "parser_recall": _recall(unexplained, substantive),
        "baseline_precision": _precision(baseline_rows),
        "baseline_recall": _recall(baseline_unexplained, substantive),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="path for the metrics JSON")
    args = parser.parse_args()
    metrics = compute_metrics()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
