# Interview notes

## The problem

Readily maps regulatory changes to health-plan policies and needs every flag tied to exact rule text and defensible to a regulator. This project builds the checkable federal half on public law: for every Federal Register document touching 42 CFR Part 438 since 2016, which sections changed, whether and when the change appears in the point-in-time eCFR, which eCFR changes no tagged document explains, and whether a quoted citation is in force at a date.

## Why this approach

Use pinned public-domain data and deterministic Python so every number can be checked by anyone, with no network and no LLM in this milestone. The specification puts a React viewer, DHCS letters, LLM calls and Postgres out of scope for now: the viewer needs the TypeScript pipeline, the letters are the next milestone, LLM flags need a ground truth first, and Postgres adds nothing for a few MB of data. No other implementation alternatives are recorded in the decision.

## Architecture

A Python package, regtrace, with frozen dataclasses in model.py. data.py loads and caches the pinned eCFR and Federal Register files. labels.py assigns CFR paragraph paths. diff.py compares eCFR dates. fr.py parses amendatory instructions. reconcile.py matches rule sections to substantive eCFR versions and finds unexplained changes. cite.py verifies quotes. api.py exposes JSON-only FastAPI endpoints. experiment.py writes metrics. Tests use unittest.

## Data flow

Pinned upstream eCFR XML and versions JSON plus Federal Register document JSON and XML go into parsing: Part 438 sections and paragraph labels, diffs between consecutive eCFR dates, and amendatory instructions from Federal Register text. Reconciliation then maps rule sections to substantive eCFR versions and produces rows and an unexplained list. Citation verification checks quotes against point-in-time text. The API and experiment read from the same library.

## Trade-offs

eCFR is an editorial compilation, not the official legal edition. Federal Register CFR tagging may miss documents, so the unexplained list is evidence rather than proof of error. A rule's own applicability dates inside regulation text are not parsed yet. Only federal rules are covered, not state letters. Milestone 1 has no LLM, Postgres or React viewer. The label parser follows explicit rules, but the review says two specified behaviors still lack direct regression tests. The baseline has higher recall but much lower precision than the parser.

## Results

The acceptance suite passed 42/42 and the project's own suite passed 149/149. The independent review says both earlier blocking findings were fixed and found no new behavioral defect; it still returned changes because instruction carry-over across REGTEXT blocks and label progression past z to aa lack direct regression tests. Measured metrics include 38 dates, 45 documents and 26 rules; parser precision 0.955056 and recall 0.89441; baseline precision 0.431298 and recall 0.913043; citation self-valid 1.0 and perturbed rejected 1.0. Other counts include 74 matched, 11 shifted, 7 before history, 4 unmatched, 17 unexplained, 2,281 latest paragraphs and 732 paragraph changes.

## Limitations

The tool is not a legal edition and does not replace the official CFR. It can only reconcile documents that the Federal Register tagging surfaces; missed tagging shows up as unexplained changes. It does not yet parse applicability dates written inside regulation text. It covers federal rules only, not DHCS All Plan Letters or other state guidance. It does not include the React viewer, an LLM layer or Postgres. The review verdict is changes, so two parser regression tests should be added before calling the test coverage complete.

## What I learned

Traceability is mostly a data-model and edge-case problem: CFR paragraph labels are ambiguous and date matching needs care. A pinned, checksummed snapshot makes results reproducible. Unexplained changes are useful evidence, not just errors. Independent review can find missing tests even when behavior is correct. A deterministic ground truth is a good base before LLM-made compliance flags. The project was developed with Arcturus, Yash's multi-agent system, and reviewed by an independent model.

## Talking points

- The project was developed with Arcturus, Yash's multi-agent system, and reviewed by an independent model; it was not hand-written by Yash.
- Every reported number comes from pinned public federal data and code that can be rerun; nothing is typed into the README by hand.
- The parser is much more precise than the baseline: 0.955056 versus 0.431298, while baseline recall is higher: 0.913043 versus 0.89441.
- Citation checks are strong on this data: 1.0 self-valid and 1.0 perturbed rejected.
- The unexplained list is the honest edge of the method: it shows where Federal Register tagging and eCFR versions do not line up.
- The independent review returned changes only for missing regression tests, not for a new behavioral defect.
- This maps directly to Readily's need for flags tied to exact rule text: it builds the checkable federal ground truth first.
- Next steps in the spec are a React viewer, DHCS All Plan Letters, and LLM compliance flags checked against this ground truth.

## Questions to expect

**How do you know the paragraph labels are right?**

The labels follow explicit specification rules and are covered by tests. The independent review found no behavioral defect, but it did flag two specified cases that need direct regression tests.

**Why not use an LLM for this?**

Milestone 1 needed a deterministic, checkable ground truth on public law. LLM calls are out of scope here and can be tested later against this base.

**How do you handle date mismatches between the Federal Register and eCFR?**

Reconciliation marks rows matched, shifted, before history or unmatched, and lists eCFR changes that no tagged document explains. The unexplained list is the evidence.

**Why no database?**

The pinned data is only a few MB, so Postgres adds operational cost without helping this milestone.

**What is the weakest part?**

eCFR is editorial, Federal Register tagging can miss documents, applicability dates inside rule text are not parsed, and state guidance is not covered yet.

**Why is parser recall lower than the baseline?**

The baseline predicts every section number that appears anywhere in a document, which is broad. The parser is narrower and more precise, so it misses more but produces fewer false sections.

**How would this fit Readily's product?**

It builds the traceable federal citation and change layer that compliance flags need. It does not claim anything about Readily's internal product or data.
