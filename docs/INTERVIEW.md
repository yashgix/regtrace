# Interview notes

## The problem

Readily says it uses AI to "analyze regulatory updates and documents, flag what applies, identify affected policies" and "cite supporting evidence" (<https://www.readily.ai/>). This project builds a checkable federal piece of that on public law: for every Federal Register document touching 42 CFR Part 438 since 2016, which sections changed, whether and when the change appears in the point-in-time eCFR, which eCFR changes no tagged document explains, and whether a quoted citation is in force at a date.

## Why this approach

Use pinned public-domain data and deterministic Python so every number can be checked by anyone, with no network and no LLM in this milestone. The specification puts a React viewer, DHCS letters, LLM calls and Postgres out of scope for now: the viewer needs the TypeScript pipeline, the letters are the next milestone, LLM flags need a ground truth first, and Postgres adds nothing for a few MB of data. No other implementation alternatives are recorded in the decision.

## Architecture

A Python package, regtrace, with frozen dataclasses in model.py. data.py loads and caches the pinned eCFR and Federal Register files. labels.py assigns CFR paragraph paths. diff.py compares eCFR dates. fr.py parses amendatory instructions. reconcile.py matches rule sections to substantive eCFR versions and finds unexplained changes. cite.py verifies quotes. api.py exposes JSON-only FastAPI endpoints. experiment.py writes metrics. Tests use unittest.

## Data flow

Pinned upstream eCFR XML and versions JSON plus Federal Register document JSON and XML go into parsing: Part 438 sections and paragraph labels, diffs between consecutive eCFR dates, and amendatory instructions from Federal Register text. Reconciliation then maps rule sections to substantive eCFR versions and produces rows and an unexplained list. Citation verification checks quotes against point-in-time text. The API and experiment read from the same library.

## Trade-offs

eCFR is an editorial compilation, not the official legal edition. Federal Register CFR tagging may miss documents, so the unexplained list is evidence rather than proof of error. A rule's own applicability dates inside regulation text are not parsed yet. Only federal rules are covered, not state letters. Milestone 1 has no LLM, Postgres or React viewer. The parser-versus-baseline numbers measure agreement with eCFR's own version history, not verified amendment ground truth, so they compare how well each set of predicted sections lines up with eCFR's changes; they do not show which one finds amendments correctly.

## Results

The numbers live in one place: the README's generated results block, rendered by `python demo.py --readme README.md` from `results/metrics.json`, which the runner measures after the final review and checks against every claim. They cover the snapshot's shape, the reconciliation tallies (matched, shifted, before history, unmatched, unexplained), the citation self-checks, and precision and recall for the parser and for a baseline that cites every `438.N` it sees. Precision and recall here mean agreement with eCFR's own version history: whether a rule's predicted sections show a substantive eCFR change near its dates, and how many substantive changes no rule claims. They are not checked against verified amendments.

## Limitations

The tool is not a legal edition and does not replace the official CFR. It can only reconcile documents that the Federal Register tagging surfaces; missed tagging shows up as unexplained changes. It does not yet parse applicability dates written inside regulation text. It covers federal rules only, not DHCS All Plan Letters or other state guidance. It does not include the React viewer, an LLM layer or Postgres. Precision and recall are agreement with eCFR's version history, not accuracy against verified amendments.

## What I learned

Traceability is mostly a data-model and edge-case problem: CFR paragraph labels are ambiguous and date matching needs care. A pinned, checksummed snapshot makes results reproducible. Unexplained changes are useful evidence, not just errors. Independent review finds missing tests even when the behavior is right. A deterministic ground truth is a good base before LLM-made compliance flags. The project was developed with Arcturus, Yash's multi-agent system, and reviewed by an independent model.

## Talking points

- The project was developed with Arcturus, Yash's multi-agent system, and reviewed by an independent model; it was not hand-written by Yash.
- Every reported number comes from pinned public federal data and code that can be rerun; nothing is typed into the README or these notes by hand.
- The parser and the baseline are compared on agreement with eCFR's version history, read from the README's generated table: that shows how their predicted sections line up with eCFR's changes, not which one is right about amendments.
- The citation verifier is checked both ways: a section's own text must verify, and the same quote with its last word changed must not.
- The unexplained list is the honest edge of the method: it shows where Federal Register tagging and eCFR versions do not line up.
- The specified edge cases have direct regression tests, including an instruction that carries across REGTEXT blocks and labels that run from (z) to (aa).
- It gives the "cite supporting evidence" step Readily describes a checkable federal ground truth to cite.
- Next steps in the spec are a React viewer, DHCS All Plan Letters, and LLM compliance flags checked against this ground truth.

## Questions to expect

**How do you know the paragraph labels are right?**

The labels follow explicit specification rules, and each rule has a test, including the specified progression from (z) to (aa).

**Why not use an LLM for this?**

Milestone 1 needed a deterministic, checkable ground truth on public law. LLM calls are out of scope here and can be tested later against this base.

**How do you handle date mismatches between the Federal Register and eCFR?**

Reconciliation marks rows matched, shifted, before history or unmatched, and lists eCFR changes that no tagged document explains. The unexplained list is the evidence.

**Why no database?**

The pinned data is only a few MB, so Postgres adds operational cost without helping this milestone.

**What is the weakest part?**

eCFR is editorial, Federal Register tagging can miss documents, applicability dates inside rule text are not parsed, and state guidance is not covered yet.

**How should the parser and baseline numbers be read?**

As agreement with eCFR's version history only. The baseline predicts every section number that appears anywhere in a document, so it claims more sections; the parser claims only sections its amendatory instructions name. The generated table shows how often each one's sections line up with a substantive eCFR change, and how many eCFR changes each leaves unclaimed. Without verified amendment ground truth, that says how they agree with eCFR, not which one is correct.

**How would this fit Readily's product?**

It builds the traceable federal citation and change layer that compliance flags need. It does not claim anything about Readily's internal product or data.
