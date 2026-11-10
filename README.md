# regtrace

Trace every Federal Register change to 42 CFR Part 438 (Medicaid managed care) against the official
point-in-time eCFR.

regtrace is a small deterministic Python library with a read-only JSON API. For every Federal Register
document tagged to Part 438 since 2016 it answers:

- Which sections did the document amend? Amendatory instructions are parsed from the document XML.
- Did the eCFR record a substantive change on the rule's effective date (`matched`), near it (`shifted`),
  before eCFR history (`before_history`), or not at all (`unmatched`)?
- Which substantive eCFR section versions are not explained by any tagged Rule?
- Is a quoted citation actually in force for a section, label and date?

This is the checkable public-law half of regulatory change management. It is not legal advice and it does
not decide whether a health plan is compliant.

## Why it matters

Medi-Cal plans and their vendors have to turn a stream of federal and state changes into policy edits,
owner assignments and audit evidence. The hard part is not fetching a PDF; it is keeping the chain from
rule text to policy change defensible months later.

Readily describes its product as an AI-native compliance intelligence platform for healthcare:

> Readily is an AI-native compliance intelligence platform for healthcare. It connects regulatory
> requirements with policies, assigned actions, audits and supporting evidence, so compliance teams can
> see what changed, who owns the response and whether the work is complete.

Source: <https://www.readily.ai/>

Its own description of the AI surface is:

> Readily uses AI to analyze regulatory updates and documents, flag what applies, identify affected
> policies, draft redlines and audit assessments, cite supporting evidence and scrub data for errors.

Source: <https://www.readily.ai/>

It also states a product boundary that keeps humans in the loop:

> It does not approve policies, submit filings, close corrective action plans (CAPs) or communicate
> with regulators.

Source: <https://www.readily.ai/>

regtrace is independent and unaffiliated. It uses public federal data only and makes no claim about
Readily's customers, data, accuracy or internal implementation. What it demonstrates is the evidence
layer such work needs: point-in-time text, explicit matching rules, a list of changes nobody explains,
and a citation verifier that fails closed.

## Data in this repository

`upstream/` is a pinned snapshot of US federal works (public domain):

- `upstream/ecfr/part438-YYYY-MM-DD.xml`: the full eCFR XML of 42 CFR Part 438 on each date a section
  changed. The snapshot has 38 dates, from 2017-01-01 (the start of eCFR history) to 2026-07-31.
- `upstream/ecfr/versions.json`: eCFR section versions with `substantive` and `removed` flags.
- `upstream/fr/documents.json`: 45 Federal Register documents tagged to 42 CFR 438 since 2016, oldest
  first. 26 are Rules; the rest are Proposed Rules and related notices.
- `upstream/fr/<document_number>.xml`: full text for documents that have it.

`upstream/MANIFEST.json` records the source URL, SHA-256 and byte size of every file, plus the fetch
time (2026-11-10T07:19:08+00:00). Verify the snapshot with:

```sh
python3 tools/fetch_data.py --verify
```

The repository never needs the network at test time. All parsing is local XML and JSON.

## Run

```sh
make test
make lint
make data-check
python experiment.py --out results/metrics.json
python demo.py --readme README.md
uvicorn regtrace.api:app --reload
```

`make test` runs the `unittest` suite. `make lint` runs ruff. `make data-check` checks the pinned
checksums. `experiment.py` writes deterministic metrics. `demo.py` renders the evidence block below
and, with `--readme`, refreshes it in place; without that flag it prints the same Markdown to stdout,
so a reviewer can diff the tables without touching this file. The API is read-only.

## Results

Three counts are fixed by the snapshot and asserted by the test suite:

| item | count |
|---|---:|
| eCFR snapshot dates | 38 |
| Federal Register documents | 45 |
| Rule documents | 26 |

Every other number here is computed, never typed. `experiment.py` writes a numbers-only metrics
object (snapshot counts, reconciliation tallies, citation self-checks and perturbation checks, and
parser-versus-baseline precision and recall) to `results/metrics.json`. `demo.py` renders that object
together with `reconcile()` into the block below, which is the only generated part of this file.

Two of the tables are the point of the project. **Unexplained changes** lists every substantive
`(section, date)` that no Rule row claims, with the section heading and the next human check.
**Discrepancies** lists every `shifted` or `unmatched` row with document, section, expected date,
eCFR date and status. Change the snapshot, re-run `python demo.py --readme README.md`, and both
tables change with it.

<!-- regtrace:evidence:start -->

_Run `python demo.py --readme README.md` to render the metrics, unexplained changes, discrepancies and
walk-through tables into this block._

<!-- regtrace:evidence:end -->

## What the statuses mean

For each Rule document and each section its amendatory instructions predict:

- `matched`: the eCFR has a substantive version of that section on the rule's effective date (or its
  publication date when `effective_on` is null).
- `shifted`: no version on the expected date, but a substantive version exists between the publication
  date and 30 days after the expected date. The nearest date wins; ties go to the earlier date.
- `before_history`: both the expected date and the publication date are on or before 2017-01-01, so the
  eCFR cannot witness the change.
- `unmatched`: none of the above.

A row also claims `(section, publication_date)` when eCFR records a version on the day the rule was
published, because the Federal Register and eCFR often record both the publication and effective dates.
`unexplained` is every substantive `(section, date)` with date after the base date that no row claims.

## API

All responses are JSON; dates are `YYYY-MM-DD`.

- `GET /health` -> snapshot counts.
- `GET /sections/{section}?date=` -> heading and labeled paragraphs at the latest snapshot on or before
  `date` (default: latest). 404 for no data or unknown section.
- `GET /changes?from=&to=` -> section, heading and paragraph changes between two snapshot dates.
- `GET /documents` -> every Federal Register document with reconciliation status counts.
- `GET /documents/{number}` -> one document, its parsed amendatory instructions and its reconciliation
  rows. 404 for an unknown number.
- `GET /unexplained` -> the unexplained `(section, date)` list.
- `POST /verify` -> verify a quote for a section, label and date. Bad JSON shape is 422; an invalid date
  is 400.

Example request and response shapes are in `examples/`.

## Limits

- The eCFR is an editorial compilation, not the official legal edition. The official edition is the
  Federal Register and the Code of Federal Regulations as published by the Office of the Federal
  Register.
- The Federal Register's CFR tagging can miss documents. The unexplained list is the evidence of that,
  not a claim that eCFR is wrong.
- A rule's own applicability dates inside the regulatory text are not parsed yet. The reconciliation uses
  the document's effective date, or publication date when no effective date is present.
- Only federal rules are covered. State Medicaid guidance, including DHCS All Plan Letters, is out of
  scope for this milestone.
- The parser labels CFR paragraphs from their printed markers and nesting. It is deterministic and
  conservative; unusual XML forms fall back to the `~n` unlabeled form rather than guessing a label.

## Data provenance

Sources:

- eCFR versioner API: <https://www.ecfr.gov/api/versioner/v1/versions/title-42.json?part=438> and the
  point-in-time full XML at <https://www.ecfr.gov/api/versioner/v1/full/YYYY-MM-DD/title-42.xml?part=438>.
- Federal Register API: <https://www.federalregister.gov/api/v1/documents.json> filtered to 42 CFR 438.

Every downloaded file is checksummed in `upstream/MANIFEST.json`. `tools/fetch_data.py --verify` recomputes
SHA-256 and fails if a byte changed. Re-fetching is explicit; tests and the API never fetch.

## Build note

Built with Arcturus, an AI multi-agent system, and reviewed by an independent model. The code, tests and
rendered tables are the evidence; no number in the generated block is hand-entered.
