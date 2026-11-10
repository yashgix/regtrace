"""Immutable value types shared by the regtrace modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paragraph:
    label: str
    text: str


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    paragraphs: tuple[Paragraph, ...]

    def text_of(self, label: str) -> str | None:
        for paragraph in self.paragraphs:
            if paragraph.label == label:
                return paragraph.text
        return None


@dataclass(frozen=True)
class Part:
    date: str
    sections: dict[str, Section]


@dataclass(frozen=True)
class Version:
    section: str
    date: str
    substantive: bool


@dataclass(frozen=True)
class Document:
    number: str
    type: str
    action: str
    title: str
    publication_date: str
    effective_on: str | None
    has_text: bool


@dataclass(frozen=True)
class Change:
    section: str
    label: str
    kind: str
    old_text: str | None
    new_text: str | None


@dataclass(frozen=True)
class Instruction:
    document: str
    number: int
    text: str
    sections: tuple[str, ...]


@dataclass(frozen=True)
class Row:
    document: str
    section: str
    status: str
    date: str | None


@dataclass(frozen=True)
class Verdict:
    status: str
    found_label: str | None = None
    found_dates: tuple[str, ...] = ()
