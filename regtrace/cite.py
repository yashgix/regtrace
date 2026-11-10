'''Check whether a quoted citation is present at a point in time.'''

from __future__ import annotations

from pathlib import Path

from .data import DATA_DIR, dates, in_force, load_part
from .model import Verdict


def _normalize(text: str) -> str:
    return ' '.join(text.split())


def verify(section: str, label: str, date: str, quote: str, data_dir: Path = DATA_DIR) -> Verdict:
    '''Verify a quote against the in-force eCFR text for a section and label.'''
    normalized = _normalize(quote)
    if len(normalized) < 20:
        return Verdict('too_short')

    effective = in_force(date) if data_dir == DATA_DIR else in_force(date, data_dir)
    if effective is None:
        return Verdict('no_data')

    part = load_part(effective) if data_dir == DATA_DIR else load_part(effective, data_dir)
    section_obj = part.sections.get(section)
    if section_obj is not None:
        text = section_obj.text_of(label)
        if text is not None and normalized in _normalize(text):
            return Verdict('valid')
        for paragraph in section_obj.paragraphs:
            if paragraph.label != label and normalized in _normalize(paragraph.text):
                return Verdict('wrong_paragraph', found_label=paragraph.label)

    all_dates = dates() if data_dir == DATA_DIR else dates(data_dir)
    found = []
    for other in all_dates:
        if other == effective:
            continue
        other_part = load_part(other) if data_dir == DATA_DIR else load_part(other, data_dir)
        other_section = other_part.sections.get(section)
        if other_section is None:
            continue
        other_text = other_section.text_of(label)
        if other_text is not None and normalized in _normalize(other_text):
            found.append(other)

    if found:
        return Verdict('other_date', found_dates=tuple(found))
    return Verdict('not_found')
