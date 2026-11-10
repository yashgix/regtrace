"""Read amendatory instructions for 42 CFR Part 438 from Federal Register XML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .data import DATA_DIR, document_xml, section_key, versions
from .model import Instruction

_SECTION = re.compile(r"438[.]([0-9]+[a-z]?)")
_RANGE = re.compile(r"438[.]([0-9]+[a-z]?) through 438[.]([0-9]+[a-z]?)", re.IGNORECASE)
_NUMBERED = re.compile(r"([0-9]+)[.]")


@dataclass
class _Instruction:
    number: int
    parts: list[str] = field(default_factory=list)
    sections: set[str] = field(default_factory=set)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _text(element) -> str:
    return _normalize("".join(element.itertext()))


def _number(section: str) -> int | None:
    match = re.fullmatch(r"438[.]([0-9]+)[a-z]?", section)
    return int(match.group(1)) if match else None


def _references(text: str) -> set[str]:
    return {f"438.{match.group(1)}" for match in _SECTION.finditer(text)}


def _expand(start: str, end: str, known: list[str]) -> set[str]:
    start_number = _number(start)
    end_number = _number(end)
    if start_number is None or end_number is None:
        return set()
    low, high = sorted((start_number, end_number))
    return {
        section
        for section in known
        if (number := _number(section)) is not None and low <= number <= high
    }


def instructions(number: str, data_dir: Path = DATA_DIR) -> list[Instruction]:
    """Return the AMDPAR instructions of one Federal Register document."""
    xml = document_xml(number) if data_dir == DATA_DIR else document_xml(number, data_dir)
    if xml is None:
        return []

    root = ET.fromstring(xml)
    all_versions = versions() if data_dir == DATA_DIR else versions(data_dir)
    known = sorted({version.section for version in all_versions}, key=section_key)
    pending: list[_Instruction] = []
    current: _Instruction | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            pending.append(current)
            current = None

    def visit(element, in_part: bool) -> None:
        nonlocal current
        tag = _local(element.tag)
        if tag == "REGTEXT":
            in_part = element.get("PART") == "438"
        if in_part and tag == "AMDPAR":
            text = _text(element)
            if text:
                numbered = _NUMBERED.match(text)
                if numbered:
                    flush()
                    current = _Instruction(int(numbered.group(1)), [text])
                elif current is None:
                    current = _Instruction(0, [text])
                else:
                    current.parts.append(text)
        elif in_part and tag == "SECTNO" and current is not None:
            current.sections.update(_references(_text(element)))
        for child in element:
            visit(child, in_part)

    visit(root, False)
    flush()

    result = []
    for instruction in pending:
        text = " ".join(instruction.parts)
        sections = set(instruction.sections)
        sections.update(_references(text))
        for start, end in _RANGE.findall(text):
            sections.update(_expand(f"438.{start}", f"438.{end}", known))
        result.append(
            Instruction(
                number,
                instruction.number,
                text,
                tuple(sorted(sections, key=section_key)),
            )
        )
    return result
