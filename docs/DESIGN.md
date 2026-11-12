# Design

## Goal and shape

regtrace is a deterministic evidence tool, not a compliance decision system. The snapshot is fixed; the
library parses it, compares dates, and lists its own gaps. The public surface is a small set of frozen
dataclasses in `regtrace/model.py`; each module consumes those values rather than passing XML around.

There are four separable jobs:

1. turn eCFR XML into labeled paragraphs;
2. diff two labeled snapshots;
3. parse Federal Register amendatory instructions into section claims;
4. reconcile those claims against eCFR section versions and verify quoted citations.

Keeping the jobs separate makes each kind of gap easier to trace. A labeling problem tends to show up
as an unlabeled paragraph; a missing claim shows up as an unexplained `(section, date)`; a citation miss
shows up as a failed substring check.

## Labeling CFR paragraphs

CFR paragraph markers are printed text, not structured XML. `(i)` can be the ninth letter in a list or
roman numeral one. The labeler therefore walks the paragraph stream and maintains a stack of
`(level, symbol, headed)` entries. `label_paragraphs(div8)` returns tuples of `Paragraph(label, text)`.

### Text and inline pieces

The XML is flattened to characters plus the innermost italic element id for each character. Whitespace
runs collapse to one space and the result is stripped. XML entities are already decoded by
`ElementTree`. Markers stay in the text; a paragraph labeled `(i)` still begins `(i) ...`.

A single `P` can hold several logical paragraphs. After an italic run ends, the parser skips spaces,
optionally skips one `-` or em dash, skips spaces again, and checks for a valid marker. If one follows, the
paragraph is cut there and the dash is dropped. This handles `</I>-(1)`, `</I> - (1)` and the no-dash form
`</I> (1)`.

### Marker grammar

A marker is `(symbol)` where the symbol is one of:

- one or two lowercase letters;
- one to six characters from `i`, `v`, `x`, `l`;
- one uppercase letter;
- one to three digits.

Anything else, such as `(ILOS)`, is ordinary text. The marker may be plain, `(<I>x</I>)`, or `<I>(x)</I>`;
the latter two carry an italic id for the symbol. Levels 0-3 require a non-italic symbol; levels 4-5 accept
an italic one. Apart from that constraint, italics do not choose the level: the main stack places a symbol
by its alphabet and its position in the stack. Italics also feed headed detection, and the definition stack
accepts non-italic markers only.

### Levels and alphabets

The main stack uses:

| level | alphabet |
|---|---|
| 0 | lowercase `a` to `z`, then `aa` to `zz` |
| 1 | digits `1` to `100` |
| 2 | lowercase roman `i` to `xxv` |
| 3 | uppercase `A` to `Z` |
| 4 | digits `1` to `100` |
| 5 | lowercase roman `i` to `xxv` |

`depth` is the last stack level plus one, or zero for an empty stack. A marker can **open** level L only
when L equals depth and the symbol is the first symbol of L's alphabet. It can **continue** level L when
the stack already has an entry at L and the symbol is the next symbol in L's alphabet.

When both are possible, opening wins. The exception is a headed piece: the markers are directly followed
by an italic element whose text does not start with `(`. If that piece can continue a headed entry, the
continuation wins over opening a deeper level. This matches the common CFR form where a new italic
heading continues the same level after a run of definitions or lists.

If no rule fits, the piece is not treated as a marker at that position. A successful placement keeps the
entries below the chosen level and replaces the rest with the new entry.

### Definitions

A piece with no placed marker can open a definition when it starts with an italic element whose text does
not start with `(` and that element has no child elements. The term is the whole normalized italic text
with a trailing `.` or `,` removed, parentheses and all; its label is the current main path plus `def:`
plus the term, for example `def:Abuse`, `def:Health insuring organization (HIO)` or
`(a)def:Academic medical center`.

Inside a definition, markers are placed on a separate stack using digits, lowercase roman, and uppercase
(all non-italic). The first child may open any of those levels, which is why
`def:Health insuring organization (HIO)(3)(i)` works even though the first marker is `(3)`. A marker that
does not fit the definition stack ends the definition; that same marker is then tried on the main stack.

### Unlabeled pieces

Anything else gets `<last label>~<n>`, with `n` counting from one since the last labeled piece. A section
that opens with unmarked text gets `~1`. A repeated label is also demoted this way, so labels are unique
within a section at every date. This is deliberately conservative: an unfamiliar XML shape becomes visible
as an unlabeled paragraph instead of a silently wrong citation label.

## Diffs

`diff(old, new)` visits the union of section ids in `section_key` order. A section only in new yields one
`section_added`; only in old yields `section_removed`. Otherwise a changed heading yields
`heading_revised`, then new labels appear in new order as `added` or `revised`, then labels only in old
appear in old order as `removed`. Duplicate labels are paired in order of appearance, so a repeated `(a)`
does not swallow its twin. Texts are carried for revision, addition and removal so a reviewer can see
exactly what changed.

## Amendatory instructions

`fr.instructions(number)` reads only `REGTEXT` blocks whose `PART` attribute is `438`. It walks `AMDPAR`
and `SECTNO` elements in document order:

- an `AMDPAR` beginning with `N.` starts instruction N;
- an unnumbered `AMDPAR` is appended to the current instruction text, or starts instruction 0 if none;
- `SECTNO` headings attach their `438.N` references to the current instruction;
- sections also come from references in instruction text and from ranges such as `438.2 through 438.10`.

Ranges expand against section ids present in `versions()`, since a range cannot name a section eCFR has
never seen. Results are deduplicated and sorted by `section_key`. A document without full text has no
instructions, and neither does a document that states its change outside `REGTEXT`, as some CFR
corrections do; its change can then appear as unexplained.

## Reconciliation

Only documents of type `Rule` participate, in file order. For each document the predicted sections are
deduplicated and sorted. By default prediction is the union of its parsed amendatory instruction sections;
`reconcile` also accepts a `predict` callable for the baseline experiment.

The base date is the earliest version date, 2017-01-01. `have` is the set of `(section, date)` pairs for
substantive versions. `expected` is `effective_on`, or `publication_date` when that is null.

For each document and predicted section:

- `before_history`, date `None`, when both expected and publication date are on or before the base date;
- `matched`, date expected, when `(section, expected)` is in `have`;
- `shifted`, date of the nearest version, when a substantive version exists in
  `[publication_date, expected + 30 days]`; ties go to the earlier date;
- `unmatched`, date `None`, otherwise.

A non-`before_history` row also claims `(section, publication_date)` when eCFR has a substantive version on
the publication day, and matched or shifted rows claim their row date. `unexplained` is every substantive
`(section, date)` after the base date that no row claims, sorted by date and then section.

The 30-day window is a compromise. eCFR sometimes records a version a few days after the rule's effective
date, and sometimes on the publication date as well as the effective date. A wider window would claim
unrelated changes and hide real gaps; a narrower one would create false `unmatched` rows. Ties going
earlier keep the result stable. `before_history` precedence prevents 2016 rules from looking like eCFR
failures when eCFR history simply starts on 2017-01-01.

## Citation verification

`cite.verify(section, label, date, quote)` normalizes whitespace on both sides and applies statuses in this
order:

1. `too_short` when the normalized quote is under 20 characters;
2. `no_data` when `in_force(date)` is `None`;
3. `valid` when the section has that label and the quote is a substring of its normalized text;
4. `wrong_paragraph` when the quote appears in another paragraph of the same section, returning the first
   such label in section order;
5. `other_date` when the quote appears under the same section and label at other data dates, returning all
   such dates ascending;
6. `not_found`.

The 20-character floor keeps a citation check from passing on a phrase like `the State`. `wrong_paragraph`
beats `other_date` because pointing at the right date but wrong label is a more useful correction than a
date hunt.

## Experiment and baseline

`experiment.py` writes only numbers. It counts snapshots, latest sections and paragraphs, unlabeled
paragraphs, paragraph changes between consecutive dates, documents, rules, rules with instructions,
instructions, rows, every status, unexplained changes, citation self-validity and perturbed rejection, and
parser versus baseline precision and recall.

Precision is `(matched + shifted) / (rows - before_history)`. Recall is
`1 - unexplained / substantive versions with date != base`. Both are measured through `reconcile`, so the
parser and baseline see the same version set and the same claim rules. They measure agreement with eCFR's
own version history on one pinned snapshot, not accuracy: nothing here is checked against independently
verified amendments.

The baseline predicts every section matching `438.` plus digits and an optional letter anywhere in the raw
document XML. The parser uses only amendatory text and `SECTNO` headings inside `REGTEXT`. A predicted
section with no substantive eCFR change near the rule's dates lowers precision; a substantive change no
row claims lowers recall. That is as far as these numbers go: they show how each prediction set lines up
with eCFR's history on this snapshot, not why a section was or was not amended. Reporting both keeps the
trade-off visible instead of folding it into one number.

## API surface

`create_app(data_dir=DATA_DIR)` builds the FastAPI app; the module-level `app` is the default-snapshot
instance. Tests pass a temporary snapshot directory, so every endpoint takes its data from the app's
directory and reconciliation is cached per directory. The surface is read-only:

- `GET /sections/{section}?date=` resolves the date with `in_force`, so a request inside a gap returns the
  text that was actually in force and reports it as `in_force`;
- `GET /changes?from=&to=` refuses anything that is not a snapshot date (400) rather than silently diffing
  the nearest one;
- `GET /documents` and `GET /documents/{number}` share one reconciliation result, so the status counts in a
  list entry always equal the counts of that document's rows;
- `POST /verify` takes a Pydantic body (shape errors are 422) and rejects a non-ISO date with 400.

## Rendering the evidence

`demo.py` is the only place that turns numbers into prose tables. `render(metrics)` returns the metrics
table, the unexplained changes table, the discrepancies table and a walk-through that also perturbs one
quote to show the citation verifier rejecting it. Cells are whitespace-normalized and pipe-escaped so a
heading cannot break a table; an empty list renders as `_None._` rather than a header with no body.

`render_readme(metrics, README.md)` splices that block into the README between
`<!-- regtrace:evidence:start -->` and `<!-- regtrace:evidence:end -->` and leaves the prose untouched. The
README is therefore partly hand-written narrative and partly generated evidence, with a hard boundary
between the two.

## Determinism and caching

Parsed files are cached with `functools.lru_cache` keyed by date and `Path`, so each eCFR snapshot is read
once per process. `dates`, `versions`, `documents` and `document_xml` are cached the same way. The metrics
JSON uses sorted keys and no timestamps, so repeated runs on the same snapshot are byte-identical. Tests
use synthetic XML wherever possible and the pinned snapshot only for cheap checks. No test or endpoint
opens a socket.

## Deliberately out of scope

The React viewer, DHCS All Plan Letters and other state guidance, any LLM compliance flagging, Postgres,
PDF parsing, and parsing applicability dates from inside regulation text are out of scope for this
milestone. The library is the deterministic evidence those later layers would be checked against.
