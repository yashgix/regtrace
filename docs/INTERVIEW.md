# Interview notes

## One-minute explanation

I built a small system that traces federal changes to 42 CFR Part 438, the Medicaid managed care rules,
against the official point-in-time eCFR. It parses the Federal Register amendatory instructions for every
Rule tagged to Part 438 since 2016, predicts which sections each rule amended, and then asks whether the
eCFR actually shows a substantive version on the effective date. If not, it looks for a nearby version and
otherwise reports the rule as unmatched. It also lists eCFR changes that no tagged rule explains, and it
verifies a quoted citation against the text in force on a chosen date.

The important part is not the API. It is that every result is reproducible from a pinned public snapshot,
and the system is honest about what it cannot explain.

## Why this problem

Regulatory change management is an evidence problem. A health plan has to show why a policy changed, when
the underlying rule took effect, and which citation supports the conclusion. That is hard to do with PDFs
and spreadsheets because the text is not point-in-time and the chain of evidence is not executable.

This project is the public-law checking layer for that work. Readily's public description says it is an
AI-native compliance intelligence platform that connects regulatory requirements with policies, assigned
actions, audits and supporting evidence (source: <https://www.readily.ai/>). regtrace is not that product
and makes no claim about it. It demonstrates the ground truth such a product needs: labeled text, explicit
matching rules, an unexplained list, and a citation verifier that rejects a quote when it is not actually
in force.

## What was hard

### Paragraph labels are inferred, not read

The eCFR XML gives paragraphs and italics, but not semantic labels. `(i)` may be a letter or a roman
numeral. The labeler has to reconstruct the printed hierarchy from marker order, nesting depth, italics,
and the sequence of symbols. The tricky cases are chained markers like `(d)(1)`, inline splits after an
italic heading, definitions with their own sub-list, and headed continuations that should continue a level
instead of opening a deeper one. Italics turn out to be a narrow signal: levels 0-3 need a non-italic
symbol, levels 4-5 accept either, and headed detection uses a following italic run. I made the parser
conservative: when a marker does not fit the stack, the paragraph becomes `~n` rather than a guessed
label.

### Point-in-time matching is not exact

eCFR is an editorial compilation. A rule can be published on one date, effective on another, and appear
in eCFR on a third. Sometimes eCFR records a version on the publication date as well as the effective date.
The reconciliation therefore has `matched`, `shifted`, `before_history` and `unmatched`, plus a claim rule
for publication-date versions. The 30-day window is a deliberate trade-off: wide enough for editorial lag,
narrow enough that unrelated amendments do not get claimed.

### The gaps are the product

The unexplained list is not a bug report; it is evidence. It shows where the Federal Register's CFR
tagging, the amendatory instruction parser, or eCFR's version history disagree. That is more useful than a
single precision number, which is why the experiment reports parser and baseline precision and recall
separately.

## How I would demo it

1. Run `make test` and `python experiment.py --out results/metrics.json` to show the snapshot and the
   deterministic metrics.
2. Run `python demo.py --readme README.md` and show the unexplained changes and discrepancies tables that
   were rendered from `reconcile()`.
3. Open `uvicorn regtrace.api:app`, fetch `/sections/438.68?date=2026-07-31`, and show the labeled
   paragraphs.
4. Post a valid quote to `/verify`, then change the last word and show that it no longer verifies.
5. Fetch `/unexplained` and explain one item: which section changed, on what date, and what a human would
   check next in the Federal Register.

## Trade-offs I would defend

- Frozen dataclasses and tuple-returning APIs keep the data easy to reason about and safe to cache.
- `lru_cache` keyed by `Path` and date keeps the test suite fast without a database.
- The parser is conservative about labels. A visible `~n` is better than a wrong citation.
- The API is read-only and JSON-only. There is no mutation surface to secure yet.
- The metrics JSON has no timestamps and sorted keys so two runs can be compared byte for byte.
- The README's evidence block is generated, not typed: prose can be edited freely without risking a stale
  or invented number.

## What is next

- A React viewer over the existing API: section timeline, diff view, unexplained queue, citation checker.
- DHCS All Plan Letters and other state Medicaid guidance, with the same point-in-time and evidence model.
- LLM-made compliance flags checked against this ground truth: the model can propose that a policy clause
  is affected, but the citation and effective date are verified here.
- Parsing applicability dates from regulation text instead of relying only on the Federal Register
  metadata.
- A reviewer workflow for unexplained changes, with an explicit reason code when a change is accepted as
  out of scope.

## Questions I would ask

- Which sources are authoritative for a Medi-Cal plan: federal rules, CMS guidance, DHCS letters, or the
  contract?
- How long does a compliance team need to keep the evidence chain for an audit?
- When a rule changes, who signs off that a policy redline is complete?
- What false-positive rate is tolerable for a compliance flag that a human must review?
