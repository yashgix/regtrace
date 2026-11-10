"""Diff two parsed Part snapshots into ordered Change records."""

from __future__ import annotations

from .data import load_part, section_key
from .model import Change, Part


def diff(old: Part, new: Part) -> list[Change]:
    """Return section, heading, and paragraph changes from old to new."""
    changes: list[Change] = []
    for section_id in sorted(set(old.sections) | set(new.sections), key=section_key):
        old_section = old.sections.get(section_id)
        new_section = new.sections.get(section_id)
        if old_section is None:
            changes.append(Change(section_id, "", "section_added", None, None))
            continue
        if new_section is None:
            changes.append(Change(section_id, "", "section_removed", None, None))
            continue
        if old_section.heading != new_section.heading:
            changes.append(Change(section_id, "", "heading_revised", old_section.heading, new_section.heading))
        old_paragraphs = list(old_section.paragraphs)
        new_paragraphs = list(new_section.paragraphs)
        occurrences: dict[str, list[int]] = {}
        for index, paragraph in enumerate(old_paragraphs):
            occurrences.setdefault(paragraph.label, []).append(index)
        matched: set[int] = set()
        used: dict[str, int] = {}
        for paragraph in new_paragraphs:
            seen = used.get(paragraph.label, 0)
            candidates = occurrences.get(paragraph.label, ())
            if seen < len(candidates):
                index = candidates[seen]
                matched.add(index)
                old_text = old_paragraphs[index].text
                if old_text != paragraph.text:
                    changes.append(Change(section_id, paragraph.label, "revised", old_text, paragraph.text))
            else:
                changes.append(Change(section_id, paragraph.label, "added", None, paragraph.text))
            used[paragraph.label] = seen + 1
        for index, paragraph in enumerate(old_paragraphs):
            if index not in matched:
                changes.append(Change(section_id, paragraph.label, "removed", paragraph.text, None))
    return changes


def changes_between(a: str, b: str) -> list[Change]:
    """Diff two snapshot dates."""
    return diff(load_part(a), load_part(b))
