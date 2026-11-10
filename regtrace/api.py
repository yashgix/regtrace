"""FastAPI surface over the regtrace library."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date as Date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .cite import verify as verify_citation
from .data import DATA_DIR, dates, documents, in_force, load_part
from .diff import diff
from .fr import instructions
from .model import Document
from .reconcile import reconcile


class VerifyRequest(BaseModel):
    section: str
    label: str
    date: str
    quote: str


def _parse_date(value: str) -> str:
    try:
        parsed = Date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail=f"invalid date: {value!r}")
    return value


def _require_data_date(value: str, data_dir: Path) -> str:
    _parse_date(value)
    if value not in dates(data_dir):
        raise HTTPException(status_code=400, detail=f"{value} is not an eCFR snapshot date")
    return value


@lru_cache(maxsize=None)
def _reconciliation(data_dir: Path):
    return reconcile(data_dir=data_dir)


def _status_counts(data_dir: Path) -> dict[str, dict[str, int]]:
    rows, _ = _reconciliation(data_dir)
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        counts[row.document][row.status] += 1
    return {number: dict(sorted(counter.items())) for number, counter in counts.items()}


def _document_payload(document: Document, statuses: dict[str, int]) -> dict:
    return {
        "number": document.number,
        "type": document.type,
        "action": document.action,
        "title": document.title,
        "publication_date": document.publication_date,
        "effective_on": document.effective_on,
        "has_text": document.has_text,
        "statuses": statuses,
    }


def create_app(data_dir: Path = DATA_DIR) -> FastAPI:
    data_path = Path(data_dir)
    app = FastAPI(title="regtrace", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, int]:
        docs = documents(data_path)
        return {
            "dates": len(dates(data_path)),
            "documents": len(docs),
            "rules": sum(1 for document in docs if document.type == "Rule"),
        }

    @app.get("/sections/{section}")
    def section(section: str, date: str | None = None) -> dict:
        all_dates = dates(data_path)
        if not all_dates:
            raise HTTPException(status_code=404, detail="no eCFR snapshots")
        requested = all_dates[-1] if date is None else _parse_date(date)
        effective = in_force(requested, data_path)
        if effective is None:
            raise HTTPException(status_code=404, detail=f"no eCFR data on or before {requested}")
        part = load_part(effective, data_path)
        found = part.sections.get(section)
        if found is None:
            raise HTTPException(status_code=404, detail=f"section {section} not found at {effective}")
        paragraphs = [{"label": paragraph.label, "text": paragraph.text} for paragraph in found.paragraphs]
        return {
            "section": section,
            "date": requested,
            "in_force": effective,
            "heading": found.heading,
            "paragraphs": paragraphs,
        }

    @app.get("/changes")
    def changes(
        from_: Annotated[str | None, Query(alias="from")] = None,
        to: Annotated[str | None, Query()] = None,
    ) -> dict:
        if from_ is None or to is None:
            raise HTTPException(status_code=400, detail="from and to are required data dates")
        _require_data_date(from_, data_path)
        _require_data_date(to, data_path)
        records = diff(load_part(from_, data_path), load_part(to, data_path))
        return {
            "from": from_,
            "to": to,
            "changes": [
                {
                    "section": change.section,
                    "label": change.label,
                    "kind": change.kind,
                    "old_text": change.old_text,
                    "new_text": change.new_text,
                }
                for change in records
            ],
        }

    @app.get("/documents")
    def list_documents() -> list[dict]:
        counts = _status_counts(data_path)
        return [_document_payload(document, counts.get(document.number, {})) for document in documents(data_path)]

    @app.get("/documents/{number}")
    def document_detail(number: str) -> dict:
        document = next((item for item in documents(data_path) if item.number == number), None)
        if document is None:
            raise HTTPException(status_code=404, detail=f"document {number} not found")
        counts = _status_counts(data_path)
        rows, _ = _reconciliation(data_path)
        return {
            "document": _document_payload(document, counts.get(number, {})),
            "instructions": [
                {"number": item.number, "text": item.text, "sections": list(item.sections)}
                for item in instructions(number, data_path)
            ],
            "rows": [
                {"section": row.section, "status": row.status, "date": row.date}
                for row in rows
                if row.document == number
            ],
        }

    @app.get("/unexplained")
    def list_unexplained() -> list[dict]:
        _, items = _reconciliation(data_path)
        return [{"section": section, "date": day} for section, day in items]

    @app.post("/verify")
    def verify(request: VerifyRequest) -> dict:
        _parse_date(request.date)
        verdict = verify_citation(request.section, request.label, request.date, request.quote, data_path)
        return {
            "status": verdict.status,
            "found_label": verdict.found_label,
            "found_dates": list(verdict.found_dates),
        }

    return app


app = create_app()
