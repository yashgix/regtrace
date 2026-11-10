"""Assign full path labels to the paragraphs of one eCFR section element."""

from __future__ import annotations

import re
from dataclasses import dataclass
from string import ascii_lowercase, ascii_uppercase

from .model import Paragraph


@dataclass(frozen=True)
class _Marker:
    symbol: str
    start: int
    end: int
    italic: bool


@dataclass(frozen=True)
class _Entry:
    level: int
    symbol: str
    headed: bool


@dataclass
class _Definition:
    prefix: str
    stack: list[_Entry]


_SYMBOL = re.compile(r"(?:[a-z]{1,2}|[ivxl]{1,6}|[A-Z]|[0-9]{1,3})")


def _roman(number: int) -> str:
    values = ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))
    out = []
    for value, symbol in values:
        count, number = divmod(number, value)
        out.append(symbol * count)
    return "".join(out)


_ROMAN = tuple(_roman(number) for number in range(1, 26))
_ALPHABETS: dict[int, tuple[str, ...]] = {
    0: tuple(ascii_lowercase) + tuple(letter * 2 for letter in ascii_lowercase),
    1: tuple(str(number) for number in range(1, 101)),
    2: _ROMAN,
    3: tuple(ascii_uppercase),
    4: tuple(str(number) for number in range(1, 101)),
    5: _ROMAN,
}
_MAIN_LEVELS = (0, 1, 2, 3, 4, 5)
_ITALIC_MAIN_LEVELS = (4, 5)
_DEFINITION_LEVELS = (1, 2, 3)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _valid_symbol(symbol: str) -> bool:
    return bool(_SYMBOL.fullmatch(symbol))


def _flatten(element) -> tuple[list[str], list[int | None], dict[int, bool]]:
    """Flatten an element to characters and the innermost italic element id for each."""
    chars: list[str] = []
    ids: list[int | None] = []
    has_child: dict[int, bool] = {}
    next_id = 0

    def emit(text: str | None, italic_id: int | None) -> None:
        if text:
            chars.extend(text)
            ids.extend([italic_id] * len(text))

    def walk(node, inherited_id: int | None) -> None:
        nonlocal next_id
        italic_id = inherited_id
        if _local(node.tag) == "I":
            italic_id = next_id
            next_id += 1
            has_child[italic_id] = bool(len(node))
        emit(node.text, italic_id)
        for child in node:
            walk(child, italic_id)
            emit(child.tail, italic_id)

    walk(element, None)
    return chars, ids, has_child


def _marker_syntax(chars: list[str], pos: int) -> bool:
    if pos >= len(chars) or chars[pos] != "(":
        return False
    close = pos + 1
    while close < len(chars) and chars[close] != ")":
        close += 1
    if close >= len(chars):
        return False
    return _valid_symbol("".join(chars[pos + 1 : close]))


def _split_inline(chars: list[str], ids: list[int | None]) -> list[tuple[list[str], list[int | None]]]:
    """Split after an italic run when optional spaces, a dash, spaces, and a marker follow."""
    cuts: list[tuple[int, int]] = []
    for index in range(1, len(chars)):
        if ids[index - 1] is None or ids[index] == ids[index - 1]:
            continue
        marker_start = index
        while marker_start < len(chars) and chars[marker_start].isspace():
            marker_start += 1
        if marker_start < len(chars) and chars[marker_start] in "-—":
            marker_start += 1
            while marker_start < len(chars) and chars[marker_start].isspace():
                marker_start += 1
        if _marker_syntax(chars, marker_start):
            cuts.append((index, marker_start))

    pieces: list[tuple[list[str], list[int | None]]] = []
    start = 0
    for end, marker_start in cuts:
        if end <= start:
            continue
        pieces.append((chars[start:end], ids[start:end]))
        start = marker_start
    if start < len(chars):
        pieces.append((chars[start:], ids[start:]))
    return pieces


def _normalize(chars: list[str], ids: list[int | None]) -> tuple[str, list[int | None]]:
    out: list[str] = []
    out_ids: list[int | None] = []
    pending_space = False
    pending_id: int | None = None
    for char, italic_id in zip(chars, ids):
        if char.isspace():
            if not pending_space:
                pending_space = True
                pending_id = italic_id
            elif pending_id != italic_id:
                pending_id = None
            continue
        if pending_space and out:
            space_id = (
                pending_id
                if pending_id is not None and out_ids[-1] == pending_id and italic_id == pending_id
                else None
            )
            out.append(" ")
            out_ids.append(space_id)
        out.append(char)
        out_ids.append(italic_id)
        pending_space = False
        pending_id = None
    return "".join(out), out_ids


def _parse_marker(text: str, ids: list[int | None], pos: int) -> _Marker | None:
    if pos >= len(text) or text[pos] != "(":
        return None
    close = text.find(")", pos + 1)
    if close < 0:
        return None
    symbol = text[pos + 1 : close]
    if not _valid_symbol(symbol):
        return None
    italic = close > pos + 1 and all(ids[index] is not None for index in range(pos + 1, close))
    return _Marker(symbol, pos, close + 1, italic)


def _leading_markers(text: str, ids: list[int | None]) -> tuple[list[_Marker], int]:
    markers: list[_Marker] = []
    pos = 0
    while True:
        marker = _parse_marker(text, ids, pos)
        if marker is None:
            break
        markers.append(marker)
        pos = marker.end
    return markers, pos


def _headed(text: str, ids: list[int | None], pos: int) -> bool:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or ids[pos] is None or text[pos] == "(":
        return False
    return pos == 0 or ids[pos - 1] != ids[pos]


def _path(stack: list[_Entry]) -> str:
    return "".join(f"({entry.symbol})" for entry in stack)


def _next_symbol(level: int, symbol: str) -> str | None:
    alphabet = _ALPHABETS[level]
    try:
        index = alphabet.index(symbol)
    except ValueError:
        return None
    return alphabet[index + 1] if index + 1 < len(alphabet) else None


def _place(stack: list[_Entry], marker: _Marker, headed: bool, levels: tuple[int, ...]) -> bool:
    depth = stack[-1].level + 1 if stack else 0
    opens = [level for level in levels if level == depth and marker.symbol == _ALPHABETS[level][0]]
    continues = [
        (index, entry)
        for index, entry in enumerate(stack)
        if entry.level in levels and _next_symbol(entry.level, entry.symbol) == marker.symbol
    ]

    if not opens and not continues:
        return False

    if opens and continues:
        headed_continues = [item for item in continues if headed and item[1].headed]
        if headed_continues:
            index, entry = max(headed_continues, key=lambda item: item[1].level)
            stack[:] = stack[:index] + [_Entry(entry.level, marker.symbol, headed)]
            return True
        level = opens[0]
        stack[:] = [entry for entry in stack if entry.level < level] + [_Entry(level, marker.symbol, headed)]
        return True

    if opens:
        level = opens[0]
        stack[:] = [entry for entry in stack if entry.level < level] + [_Entry(level, marker.symbol, headed)]
        return True

    index, entry = max(continues, key=lambda item: item[1].level)
    stack[:] = stack[:index] + [_Entry(entry.level, marker.symbol, headed)]
    return True


def _place_main(stack: list[_Entry], marker: _Marker, headed: bool) -> bool:
    # Levels 0-3 need a non-italic symbol; levels 4-5 accept either form.
    levels = _MAIN_LEVELS if not marker.italic else _ITALIC_MAIN_LEVELS
    return _place(stack, marker, headed, levels)


def _definition_level(symbol: str) -> int | None:
    if symbol.isdigit() and symbol in _ALPHABETS[1]:
        return 1
    if symbol in _ALPHABETS[2]:
        return 2
    if len(symbol) == 1 and symbol in _ALPHABETS[3]:
        return 3
    return None


def _place_definition(stack: list[_Entry], marker: _Marker, headed: bool) -> bool:
    if marker.italic:
        return False
    if not stack:
        level = _definition_level(marker.symbol)
        if level is None:
            return False
        stack.append(_Entry(level, marker.symbol, headed))
        return True
    return _place(stack, marker, headed, _DEFINITION_LEVELS)


def _definition_term(text: str, ids: list[int | None], has_child: dict[int, bool]) -> str | None:
    if not text or text[0] == "(" or ids[0] is None:
        return None
    italic_id = ids[0]
    if has_child.get(italic_id, True):
        return None
    end = 1
    while end < len(text) and ids[end] == italic_id:
        end += 1
    term = text[:end].strip().rstrip(".,").strip()
    return term or None


def label_paragraphs(div8) -> tuple[Paragraph, ...]:
    """Return the section's P and FP paragraphs with their full CFR-style labels."""
    paragraphs: list[Paragraph] = []
    main_stack: list[_Entry] = []
    definition: _Definition | None = None
    last_label = ""
    unlabeled = 0
    seen: set[str] = set()

    def emit_unlabeled(text: str) -> None:
        nonlocal unlabeled
        while True:
            unlabeled += 1
            label = f"{last_label}~{unlabeled}"
            if label not in seen:
                break
        seen.add(label)
        paragraphs.append(Paragraph(label, text))

    def emit_labeled(label: str, text: str) -> None:
        nonlocal last_label, unlabeled
        if label in seen:
            emit_unlabeled(text)
            return
        seen.add(label)
        last_label = label
        unlabeled = 0
        paragraphs.append(Paragraph(label, text))

    for element in div8:
        if _local(element.tag) not in {"P", "FP"}:
            continue
        chars, ids, has_child = _flatten(element)
        for raw_chars, raw_ids in _split_inline(chars, ids):
            text, text_ids = _normalize(raw_chars, raw_ids)
            if not text:
                continue

            markers, marker_end = _leading_markers(text, text_ids)
            piece_headed = _headed(text, text_ids, marker_end) if markers else False

            if markers and definition is not None:
                placed = True
                for marker in markers:
                    if not _place_definition(definition.stack, marker, piece_headed):
                        placed = False
                        definition = None
                        break
                if placed:
                    emit_labeled(definition.prefix + _path(definition.stack), text)
                    continue

            if markers:
                placed_any = False
                for marker in markers:
                    if not _place_main(main_stack, marker, piece_headed):
                        break
                    placed_any = True
                if placed_any:
                    emit_labeled(_path(main_stack), text)
                    continue

            term = _definition_term(text, text_ids, has_child)
            if term is not None:
                prefix = _path(main_stack) + "def:" + term
                definition = _Definition(prefix, [])
                emit_labeled(prefix, text)
            else:
                emit_unlabeled(text)

    return tuple(paragraphs)
