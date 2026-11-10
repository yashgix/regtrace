"""Match Federal Register rules to point-in-time eCFR versions."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .data import DATA_DIR, documents, section_key, versions
from .fr import instructions
from .model import Row


def _plus_days(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def _distance(day: str, anchor: str) -> int:
    return abs((date.fromisoformat(day) - date.fromisoformat(anchor)).days)


def _predicted(number: str, predict, data_dir: Path) -> list[str]:
    if predict is not None:
        return list(predict(number))
    items = instructions(number) if data_dir == DATA_DIR else instructions(number, data_dir)
    sections = []
    for instruction in items:
        sections.extend(instruction.sections)
    return sections


def reconcile(
    window_days: int = 30, predict=None, data_dir: Path = DATA_DIR
) -> tuple[list[Row], list[tuple[str, str]]]:
    """Reconcile Rule documents against substantive eCFR section versions."""
    docs = documents() if data_dir == DATA_DIR else documents(data_dir)
    versions_list = versions() if data_dir == DATA_DIR else versions(data_dir)
    rules = [document for document in docs if document.type == "Rule"]
    base = min(version.date for version in versions_list)
    have = {(version.section, version.date) for version in versions_list if version.substantive}
    by_section: dict[str, list[str]] = {}
    for version in versions_list:
        if version.substantive:
            by_section.setdefault(version.section, []).append(version.date)
    for section_dates in by_section.values():
        section_dates.sort()

    rows: list[Row] = []
    claims: set[tuple[str, str]] = set()
    for document in rules:
        expected = document.effective_on or document.publication_date
        predicted = sorted(set(_predicted(document.number, predict, data_dir)), key=section_key)
        for section in predicted:
            if expected <= base and document.publication_date <= base:
                status, row_date = "before_history", None
            elif (section, expected) in have:
                status, row_date = "matched", expected
            else:
                start = document.publication_date
                end = _plus_days(expected, window_days)
                candidates = [day for day in by_section.get(section, ()) if start <= day <= end]
                if candidates:
                    row_date = min(candidates, key=lambda day: (_distance(day, expected), day))
                    status = "shifted"
                else:
                    status, row_date = "unmatched", None

            rows.append(Row(document.number, section, status, row_date))
            if status == "before_history":
                continue
            if (section, document.publication_date) in have:
                claims.add((section, document.publication_date))
            if status == "matched":
                claims.add((section, expected))
            elif status == "shifted":
                claims.add((section, row_date))

    unexplained = sorted(
        [(section, day) for section, day in have if day != base and (section, day) not in claims],
        key=lambda item: (item[1], section_key(item[0])),
    )
    return rows, unexplained
