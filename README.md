# regtrace

Trace the Federal Register documents tagged to 42 CFR Part 438 (Medicaid managed care) since 2016 against
the official point-in-time eCFR.

regtrace is a small deterministic Python library with a read-only JSON API. For every Federal Register
document tagged to Part 438 since 2016 it answers:

- Which sections did the document amend? Amendatory instructions are parsed from the document's
  `REGTEXT` blocks.
- Did the eCFR record a substantive change on the rule's effective date (`matched`), near it (`shifted`),
  before eCFR history (`before_history`), or not at all (`unmatched`)?
- Which substantive eCFR section versions does no Rule's parsed instruction claim?
- Is a quoted citation actually in force for a section, label and date?

This is a checkable public-law piece of regulatory change management. It is not legal advice and it does
not decide whether a health plan is compliant.

## One real change, end to end

The 2024 Medicaid managed care final rule (Federal Register document `2024-08085`, published 2024-05-10,
effective 2024-07-09) carries this amendatory instruction:

> 12. Amend § 438.68 by— a. Revising paragraphs (b)(1) introductory text, (b)(1)(iii), (d)(1) and (2), and
> (e); and b. Adding paragraphs (f) through (h).

regtrace parses it into a claim on § 438.68. The eCFR has a substantive version of § 438.68 on 2024-07-09,
the effective date, so the row is `matched`. Diffing the labeled eCFR snapshots of 2024-07-05 and 2024-07-09
shows 44 paragraph changes in the section (37 added, 7 revised), including the new paragraph `(f)` on
secret shopper surveys.

The same rule also names § 438.608, but the eCFR shows no substantive change to it between the rule's
publication and 30 days after its effective date, so that row is `unmatched`. The eCFR does record
§ 438.608 and § 438.16 changing on 2024-09-24, and no reconciliation row claims either of those versions.
regtrace does not guess why. It lists both under **Unexplained changes** with the next human check. (A rule's own
delayed applicability dates are one possible reason, and they are not parsed, as *Limits* says.)

To reproduce, from the repository root:

```python
from regtrace.diff import changes_between
from regtrace.fr import instructions
from regtrace.reconcile import reconcile

rows, unexplained = reconcile()
[i.text for i in instructions("2024-08085") if i.sections == ("438.68",)]
[r for r in rows if r.document == "2024-08085" and r.section in ("438.68", "438.608")]
[c for c in changes_between("2024-07-05", "2024-07-09") if c.section == "438.68"]
[u for u in unexplained if u[0] in ("438.16", "438.608")]
```

## Why it matters

Medi-Cal plans and their vendors turn federal and state changes into policy edits, owner assignments
and audit evidence. Part of that work can be checked mechanically: which rule text changed, when the
change appears in the eCFR, and whether a quoted citation was in force on a date.

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
layer such work needs: point-in-time text, explicit matching rules, a list of changes no parsed instruction claims,
and a citation verifier that fails closed.

## How it works

Four separable jobs, one module each:

1. `regtrace/labels.py` turns eCFR XML into CFR-style labeled paragraphs (`(b)(1)(i)`, `def:Abuse`, `~1`).
2. `regtrace/diff.py` diffs two labeled snapshots into ordered change records.
3. `regtrace/fr.py` parses Federal Register amendatory instructions into section claims.
4. `regtrace/reconcile.py` and `regtrace/cite.py` reconcile those claims against eCFR section versions and
   verify quoted citations.

Keeping the jobs separate makes each kind of gap easier to trace: a labeling problem tends to show up as
an unlabeled paragraph, a missing claim as an unexplained `(section, date)`, a citation miss as a failed
substring check. The design notes are in `docs/DESIGN.md`.

## Data in this repository

`upstream/` is a pinned snapshot of US federal works (public domain):

- `upstream/ecfr/part438-YYYY-MM-DD.xml`: the full eCFR XML of 42 CFR Part 438, one file per date on which
  any section of the part changed, from the start of eCFR history onward.
- `upstream/ecfr/versions.json`: eCFR section versions with `substantive` and `removed` flags.
- `upstream/fr/documents.json`: the Federal Register documents tagged to 42 CFR 438 since 2016, oldest
  first: Rules, Proposed Rules and related notices alike.
- `upstream/fr/<document_number>.xml`: full text for documents that have it.

`upstream/MANIFEST.json` records the source URL, SHA-256 and byte size of every file, plus the fetch
time (2026-11-10T07:19:08+00:00). Verify the snapshot with:

```sh
python3 tools/fetch_data.py --verify
```

The repository never needs the network at test time. All parsing is local XML and JSON.

## Run

Python 3.12 or later:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt ruff
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
so a reviewer can diff the tables without touching this file. The API is read-only. Serving it needs
`pip install uvicorn`, which is not in `requirements.txt` because the tests use FastAPI's test client.

Example request and response shapes are in `examples/`.

## Results

No number below is typed by hand. Of the counts, the test suite asserts only the snapshot's dates,
documents and rules; every value is rendered from `results/metrics.json`, whose keys are:

- snapshot shape: `dates`, `sections_latest`, `paragraphs_latest`, `unlabeled_latest`, `paragraph_changes`;
- inputs: `documents`, `rules`, `rules_with_instructions`, `instructions`, `rule_sections`;
- reconciliation: `matched`, `shifted`, `before_history`, `unmatched`, `unexplained`;
- citation self-checks: `citation_self_valid`, `citation_perturbed_rejected`;
- parser versus baseline: `parser_precision`, `parser_recall`, `baseline_precision`, `baseline_recall`.

`experiment.py` writes that numbers-only object (snapshot counts, reconciliation tallies, citation
self-checks and perturbation checks, and parser-versus-baseline precision and recall) to
`results/metrics.json`. `demo.py` renders it together with `reconcile()` into the block below, which is the
only generated part of this file.

Two of the tables are the point of the project. **Unexplained changes** lists every substantive
`(section, date)` that no Rule row claims, with the section heading and the next human check.
**Discrepancies** lists every `shifted` or `unmatched` row with document, section, expected date,
eCFR date and status. Change the snapshot, re-run `python demo.py --readme README.md`, and both
tables change with it.

**How to read precision and recall.** They measure agreement with eCFR's own version history on this
one pinned snapshot: precision is the share of a method's predicted rows that show a substantive eCFR
change near the rule's dates, and recall is the share of substantive eCFR changes that some row claims.
They are not checked against independently verified amendments, so they are not accuracy, and running
the experiment twice shows only that they are deterministic. The parser predicts the sections its
amendatory instructions name; the baseline predicts every `438.N` that appears anywhere in the
document's XML. The two scores differ because those prediction sets differ; these numbers do not show
whether any predicted section was actually amended.

<!-- regtrace:evidence:start -->

### Metrics

| metric | value |
|---|---|
| baseline_precision | 0.431298 |
| baseline_recall | 0.913043 |
| before_history | 7 |
| citation_perturbed_rejected | 1.0 |
| citation_self_valid | 1.0 |
| dates | 38 |
| documents | 45 |
| instructions | 102 |
| matched | 74 |
| paragraph_changes | 732 |
| paragraphs_latest | 2281 |
| parser_precision | 0.955056 |
| parser_recall | 0.89441 |
| rule_sections | 96 |
| rules | 26 |
| rules_with_instructions | 20 |
| sections_latest | 106 |
| shifted | 11 |
| unexplained | 17 |
| unlabeled_latest | 16 |
| unmatched | 4 |

### Unexplained changes

| section | date | heading | next check |
|---|---|---|---|
| 438.210 | 2021-01-01 | § 438.210 Coverage and authorization of services. | No parsed instruction claims it. Check Federal Register documents around 2021-01-01 for § 438.210, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.400 | 2021-01-01 | § 438.400 Statutory basis, definitions, and applicability. | No parsed instruction claims it. Check Federal Register documents around 2021-01-01 for § 438.400, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.402 | 2021-01-01 | § 438.402 General requirements. | No parsed instruction claims it. Check Federal Register documents around 2021-01-01 for § 438.402, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.6 | 2021-01-12 | § 438.6 Special contract provisions related to payment. | No parsed instruction claims it. Check Federal Register documents around 2021-01-12 for § 438.6, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.68 | 2021-03-11 | § 438.68 Network adequacy standards. | No parsed instruction claims it. Check Federal Register documents around 2021-03-11 for § 438.68, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.340 | 2021-04-29 | § 438.340 Managed care State quality strategy. | No parsed instruction claims it. Check Federal Register documents around 2021-04-29 for § 438.340, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.4 | 2021-07-01 | § 438.4 Actuarial soundness. | No parsed instruction claims it. Check Federal Register documents around 2021-07-01 for § 438.4, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.6 | 2021-07-01 | § 438.6 Special contract provisions related to payment. | No parsed instruction claims it. Check Federal Register documents around 2021-07-01 for § 438.6, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.16 | 2024-09-24 | § 438.16 In lieu of services and settings (ILOS) requirements. | No parsed instruction claims it. Check Federal Register documents around 2024-09-24 for § 438.16, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.334 | 2024-09-24 | § 438.334 [Reserved] | No parsed instruction claims it. Check Federal Register documents around 2024-09-24 for § 438.334, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.358 | 2024-09-24 | § 438.358 Activities related to external quality review. | No parsed instruction claims it. Check Federal Register documents around 2024-09-24 for § 438.358, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.608 | 2024-09-24 | § 438.608 Program integrity requirements under the contract. | No parsed instruction claims it. Check Federal Register documents around 2024-09-24 for § 438.608, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.356 | 2024-10-02 | § 438.356 State contract options for external quality review. | No parsed instruction claims it. Check Federal Register documents around 2024-10-02 for § 438.356, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.2 | 2024-10-23 | § 438.2 Definitions. | No parsed instruction claims it. Check Federal Register documents around 2024-10-23 for § 438.2, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.358 | 2024-12-19 | § 438.358 Activities related to external quality review. | No parsed instruction claims it. Check Federal Register documents around 2024-12-19 for § 438.358, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.356 | 2025-10-01 | § 438.356 State contract options for external quality review. | No parsed instruction claims it. Check Federal Register documents around 2025-10-01 for § 438.356, including corrections written outside REGTEXT and documents the CFR tagging missed. |
| 438.72 | 2026-02-25 | § 438.72 Additional requirements for long-term services and supports. | No parsed instruction claims it. Check Federal Register documents around 2026-02-25 for § 438.72, including corrections written outside REGTEXT and documents the CFR tagging missed. |

### Discrepancies

| document | section | expected | eCFR date | status |
|---|---|---|---|---|
| 2016-31650 | 438.3 | 2016-12-30 | — | unmatched |
| 2016-31650 | 438.4 | 2016-12-30 | — | unmatched |
| 2016-31650 | 438.6 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.8 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.10 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.210 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.350 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.358 | 2016-12-30 | 2017-01-18 | shifted |
| 2016-31650 | 438.364 | 2016-12-30 | — | unmatched |
| 2016-31650 | 438.604 | 2016-12-30 | 2017-01-18 | shifted |
| 2017-04307 | 438.358 | 2017-03-03 | 2017-03-06 | shifted |
| 2019-06822 | 438.210 | 2020-01-01 | 2019-04-16 | shifted |
| 2019-06822 | 438.400 | 2020-01-01 | 2019-04-16 | shifted |
| 2019-06822 | 438.402 | 2020-01-01 | 2019-04-16 | shifted |
| 2024-08085 | 438.608 | 2024-07-09 | — | unmatched |

### Walk-through

Latest eCFR snapshot: `2026-07-31` with 106 sections.

**§ 438.68 Network adequacy standards.**
- `(a)` (a) General rule. A State that contracts with an MCO, PIHP or PAHP to deliver Medicaid services must develop and enforce network adequacy standards consistent…
- `(b)` (b) Provider-specific network adequacy standards.
- `(b)(1)` (1) Provider types. At a minimum, a State must develop a quantitative network adequacy standard, other than appointment wait times, for the following provider…

Changes from `2026-06-03` to `2026-07-31`: 3.
- `added` 438.58 (a)
- `added` 438.58 (b)
- `removed` 438.58 ~1

Citation check on `438.1(a)`: `valid`; with the last word replaced: `not_found`.

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

## Limits

- The eCFR is an editorial compilation, not the official legal edition. The official edition is the
  Federal Register and the Code of Federal Regulations as published by the Office of the Federal
  Register.
- The Federal Register's CFR tagging can miss documents, and the parser reads amendatory instructions
  only inside `REGTEXT`, so a tagged document that states its change elsewhere (some CFR corrections do)
  is not claimed either. The unexplained list is the evidence for both: it lists changes no parsed
  instruction claims. It is not a count of untagged amendments and not a claim that eCFR is wrong.
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

Every downloaded file is checksummed in `upstream/MANIFEST.json` (fetch time
2026-11-10T07:19:08+00:00). `tools/fetch_data.py --verify` recomputes SHA-256 and fails if a byte
changed; `make data-check` runs it. Re-fetching is explicit; tests and the API never fetch.

## How this was built

Yash Gupta directed the project. AI coding agents (Claude Code and an agent build pipeline) wrote most of the
code and tests, and automated model reviews checked them. Those reviews are not an external audit. The code,
tests and rendered tables are the evidence, and no number in the generated block is hand-entered.

## License

MIT for this repository's code (`LICENSE`). The files in `upstream/` are US federal government works from
the eCFR and the Federal Register, in the public domain.
