"""Load the pinned eCFR and Federal Register snapshot from upstream/."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

from .labels import label_paragraphs
from .model import Document, Part, Section, Version

DATA_DIR = Path(__file__).resolve().parent.parent / "upstream"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _section_heading(element) -> str:
    for child in element:
        if _local(child.tag) == "HEAD":
            return _normalize("".join(child.itertext()))
    return ""


def _date_from_name(name: str) -> str | None:
    prefix = "part438-"
    suffix = ".xml"
    if not (name.startswith(prefix) and name.endswith(suffix)):
        return None
    date = name[len(prefix) : -len(suffix)]
    if len(date) == 10 and date[4] == "-" and date[7] == "-":
        return date
    return None


@cache
def _dates(data_dir: Path) -> tuple[str, ...]:
    found = []
    for path in (data_dir / "ecfr").glob("part438-*.xml"):
        date = _date_from_name(path.name)
        if date is not None:
            found.append(date)
    return tuple(sorted(found))


def dates(data_dir: Path = DATA_DIR) -> list[str]:
    """Return the snapshot's eCFR dates, ascending."""
    return list(_dates(Path(data_dir)))


@cache
def _load_part(date: str, data_dir: Path) -> Part:
    if date not in _dates(data_dir):
        raise KeyError(date)
    root = ET.parse(data_dir / "ecfr" / f"part438-{date}.xml").getroot()
    sections: dict[str, Section] = {}
    for element in root.iter():
        if _local(element.tag) != "DIV8":
            continue
        section_id = element.get("N")
        if not section_id:
            continue
        sections[section_id] = Section(
            section_id,
            _section_heading(element),
            label_paragraphs(element),
        )
    return Part(date, sections)


def load_part(date: str, data_dir: Path = DATA_DIR) -> Part:
    """Parse the eCFR XML for one date; unknown dates raise KeyError."""
    return _load_part(date, Path(data_dir))


@cache
def _versions(data_dir: Path) -> tuple[Version, ...]:
    payload = json.loads((data_dir / "ecfr" / "versions.json").read_text(encoding="utf-8"))
    return tuple(
        Version(str(item.get("identifier", "")), str(item.get("date", "")), bool(item.get("substantive")))
        for item in payload.get("content_versions", ())
    )


def versions(data_dir: Path = DATA_DIR) -> list[Version]:
    """Return every section version listed by the eCFR API."""
    return list(_versions(Path(data_dir)))


@cache
def _documents(data_dir: Path) -> tuple[Document, ...]:
    payload = json.loads((data_dir / "fr" / "documents.json").read_text(encoding="utf-8"))
    docs = []
    for item in payload.get("results", ()):
        number = str(item.get("document_number", ""))
        effective_on = item.get("effective_on")
        docs.append(
            Document(
                number=number,
                type=str(item.get("type") or ""),
                action=str(item.get("action") or ""),
                title=str(item.get("title") or ""),
                publication_date=str(item.get("publication_date") or ""),
                effective_on=effective_on if isinstance(effective_on, str) and effective_on else None,
                has_text=(data_dir / "fr" / f"{number}.xml").is_file(),
            )
        )
    return tuple(docs)


def documents(data_dir: Path = DATA_DIR) -> list[Document]:
    """Return the Federal Register documents in file order."""
    return list(_documents(Path(data_dir)))


@cache
def _document_xml(number: str, data_dir: Path) -> str | None:
    path = data_dir / "fr" / f"{number}.xml"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def document_xml(number: str, data_dir: Path = DATA_DIR) -> str | None:
    """Return a document's full text XML, or None when it has none."""
    return _document_xml(number, Path(data_dir))


def in_force(date: str, data_dir: Path = DATA_DIR) -> str | None:
    """Return the latest snapshot date on or before date."""
    for candidate in reversed(_dates(Path(data_dir))):
        if candidate <= date:
            return candidate
    return None


def section_key(section_id: str) -> tuple:
    """Sort 438.2 before 438.10, and a letter suffix after its number."""
    part_text, dot, rest = section_id.partition(".")
    if not dot:
        return (10**9, 10**9, section_id)
    digits = []
    suffix_at = len(rest)
    for index, char in enumerate(rest):
        if not char.isdigit():
            suffix_at = index
            break
        digits.append(char)
    try:
        part = int(part_text)
    except ValueError:
        return (10**9, 10**9, section_id)
    number = int("".join(digits)) if digits else 0
    return (part, number, rest[suffix_at:])
