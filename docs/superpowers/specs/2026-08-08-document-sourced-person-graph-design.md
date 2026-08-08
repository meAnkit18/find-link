# Document-sourced person graph: document sub-nodes and inferred connections

## Goal

Three changes to how the person network is built and shown:

1. **Person nodes carry no raw contact detail.** Expanding a person reveals
   only the *document* sub-nodes that actually exist for them (Passport,
   Emirates ID, and whatever document types arrive later) — never a
   placeholder for a document the graph doesn't have. Phone, email, bank
   account and vehicle vertices stop being rendered.
2. **Clicking a document sub-node shows that document's full field set**, in
   the right-hand detail panel. Nothing expands inline on the canvas: the
   graph shows structure, the panel shows detail.
3. **Connections between people are inferred from matching field values
   across their documents**, scored with a confidence number, and
   traversable to degree 1/2/3 — default 1, expandable in place.

The connection rule is deliberately *lazy*: any field value on one person's
document that matches any field value on another person's document is a
candidate connection. Precision comes from the confidence score and a
filter, not from a fixed list of which fields are allowed to match.

## What already exists

Grounding, because much of this is already built and the design leans on it
rather than replacing it:

- **Attributes are already separate vertices, not columns on the person.**
  Phone, email, passport, account, vehicle and address each get their own
  vertex, hanging off the person by `HAS_PHONE`/`HAS_PASSPORT`/`LOCATED_AT`
  and friends (`person_network_service.py:28-51`).
- **Person-to-person projection already exists.**
  `person_network_service.py` projects that bipartite storage onto a
  person-only graph where an edge means "these two share something", carries
  the shared thing along as the edge's reason, and does degree-1/2/3 BFS over
  the projection (`person_network` :99-175, `MAX_DEGREE = 3` at :75).
- **Hub suppression already exists.** Connector vertices with more owners
  than `max_fanout` (default 25) are dropped from the projection and reported
  as `suppressed_hubs` — the structural guard against "everyone in this
  country is connected" (`person_network` :119-136).
- **Multiple reasons per pair already merge.** `_merge_via` accumulates every
  reason linking the same pair onto one link.
- **Properties are already schemaless.** Every vertex stores its fields in a
  single JSON `props` blob, unpacked by `entity_props.py:22-57`. Nothing
  needs to change to support arbitrary keys.
- **`DocumentVertex` is already generic** — tag `document`, only `title`
  required (`intelligence-schema/entities/document.py`).
- **Emirates ID is not modelled at all.** `extraction.py:29-36` explicitly
  routes every government ID except a passport into
  `Person.attributes.national_id`, and calls Passport "the one exception"
  that gets its own entity.

So the genuinely new work is: generalising documents, indexing field values,
and scoring. The traversal machinery is reused as-is.

## 1. Document model (ingestion)

`document` becomes the single container for every document type,
distinguished by a `document_type` field inside its existing JSON props —
not a new vertex tag per type. A new document type therefore needs no schema
change.

Changes:

- `canonical.py:9-19` — replace the `PASSPORT` member of `EntityType` with a
  general `DOCUMENT`. `HAS_PASSPORT` in `RELATIONSHIP_TYPES` becomes
  `HAS_DOCUMENT` (`{"Person"} -> {"Document"}`).
- `extraction.py:29-36` — drop the "national IDs go in
  `attributes.national_id`" rule. Any identity document the model recognises
  (passport, Emirates ID, national ID card, driving licence, ...) becomes its
  own `Document` entity with `attributes.document_type` set, plus a
  `HAS_DOCUMENT` relationship. Document fields (number, issue/expiry date,
  father's name, place of birth, ...) go in that document's attributes rather
  than being flattened onto the person.
- `normalize.py:86-89,132-138` — `deterministic_key` for a document keys on
  `document_type` + normalised number, so the same passport seen in two
  source files still dedupes to one vertex. The existing
  `normalize_national_id` and `normalize_passport_number` helpers are reused
  per document type.

The person vertex keeps only identity fields used for search (name, DOB).
Phone/email/account/vehicle vertices keep being ingested — risk scoring still
reads them — they just stop being rendered as graph sub-nodes (§6).

## 2. The value index

Answering the question left open: **the index lives in NebulaGraph itself, as
`field_value` connector vertices.** No new datastore, no Elasticsearch, no
sidecar SQLite.

At ingestion, each eligible field on a document emits:

```
person -[HAS_FIELD_VALUE {field_key, document_id, document_type}]-> field_value {value}
```

The `field_value` vertex is keyed by the **normalised value alone**, not by
`(key, value)`. That is what makes cross-key matching fall out for free: two
people attached to the same `field_value` vertex through *different*
`field_key`s is a cross-key match, through the *same* `field_key` is a
same-key match, and the distinction is readable off the edges.

Why this shape: two people whose separate documents share a father's name
become two people attached to the same connector vertex — structurally
identical to two people sharing a phone vertex, which
`person_network_service` already projects, already merges reasons for,
already caps by fanout, and already walks to degree 3. Value rarity, needed
for scoring (§3), is just that vertex's owner count, which the traversal
already computes. **No person-to-person edges are materialised.**

> This revises the earlier sketch, which precomputed scored `CONNECTED_VIA`
> person-to-person edges at ingestion. Once the index is graph-native, those
> edges are redundant: the projection derives the same links from the same
> data, and skipping them avoids a second copy of the truth that has to be
> invalidated whenever the field weights or denylist change.

Values are hung off the **person**, not off the document, so the projection
stays two hops (`person -> value -> person`) and the existing traversal needs
no new hop logic. The originating document is kept on the edge, so an
explanation can still name it.

**Eligibility.** A field emits a `field_value` vertex unless:

- its key is on the denylist — `nationality`, `gender`, `sex`, `country`,
  `document_type`, `issuer`, `issuing_authority`, `issuing_country`. These
  match constantly by coincidence and carry no signal.
- the normalised value is shorter than 3 characters, or is a bare 4-digit
  year.

Everything else is eligible, including keys nobody has seen before — that is
what keeps the rule dynamic.

**Normalisation** (applied before hashing to a vertex id): casefold, trim,
collapse internal whitespace. Values containing a digit are treated as
identifiers and additionally have `-`, `/`, `.` and spaces stripped, so
`784-1990-1234567-1` and `784 1990 1234567 1` land on one vertex.
Key-specific normalisation (transliteration, name variants) is out of scope
for v1 (§9).

## 3. Confidence

Per match, following the Fellegi–Sunter shape — a field's worth is how
unlikely it is to agree by chance:

```
c = W[field_key] × R(n) × X
```

- `W` — base weight per field key, a tunable lookup table.
  `passport_number`, `national_id`, `emirates_id`, `iban` → 0.95;
  `father_name`, `mother_name`, `address`, `dob` → 0.7; **unknown keys →
  0.5**, so a field type nobody anticipated still forms connections.
- `R(n) = 1 / (n - 1)`, where `n` is the number of distinct people attached
  to that `field_value` vertex. Two people and nobody else → 1.0. Eleven
  people → 0.1. This is the rarity term, and it is what stops a common value
  from producing confident links.
- `X` — 1.0 when both sides matched on the same `field_key`, 0.6 when the
  keys differ.

Multiple independent matches between the same pair combine by **noisy-OR**:

```
confidence = 1 - Π(1 - c_i)
```

So two medium signals (shared father's name *and* shared address) compound
into something stronger than either alone, rather than the pair being scored
by its single best field.

This is computed during projection, in `_merge_via`, from data the traversal
already has in hand. Scoring lives in its own module
(`services/connection_confidence.py`) as pure functions over
`(field_key, owner_count, same_key)` so it is testable without a graph.

## 4. Degree traversal

Unchanged machinery. In `SHARED_EDGES` (`person_network_service.py:38-47`),
`HAS_FIELD_VALUE` is added and `HAS_PASSPORT` becomes `HAS_DOCUMENT` to
follow §1. Everything downstream then works as-is: BFS to `MAX_DEGREE = 3`,
per-person `degree` annotation, fanout caps, `suppressed_hubs`,
dangling-link filtering.

Note both connector kinds stay in play. `HAS_DOCUMENT` links two people who
share *the same document vertex*; `HAS_FIELD_VALUE` links two people whose
*separate* documents happen to agree on a field. These are different claims
and both are worth surfacing, so shared-document links are scored at a flat
0.95 and merged into the same `via` list as field matches.

Second degree therefore means what was asked for: A shares a value with B, B
shares a *different* value with C, so C is second degree from A with no
direct match between them.

New: a `min_confidence` parameter filters links during projection. A link
below the threshold is dropped, and — because it is dropped before the next
level expands — cannot serve as a stepping stone to the next degree either,
which is the behaviour an investigator expects from a confidence filter.

## 5. API

- `person_network(root_id, degree, min_confidence, ...)` — new
  `min_confidence` param (default 0.0). Each returned link gains
  `confidence` and keeps its `via` reasons, each reason naming the field key,
  the matched value, and the source document.
- Person expand returns **only `document` sub-nodes**. The existing
  `attributes()` method (`person_network_service.py:175+`) is narrowed to the
  document tag for this view; `field_value` vertices are *never* returned as
  nodes — they are an index, and surface only inside link explanations.
- Document expand reuses `entity_props.merged_properties` unchanged.

## 6. Frontend

- `GraphCanvas.tsx` / `GraphCanvas3D.tsx` — the `mainTags`/`NodeRole`
  mechanism (`graphStyle.ts:30-38`) already distinguishes main from sub
  nodes; the sub set narrows to `document`. Phone/email/account/vehicle stop
  being rendered.
- Degree selector (1/2/3) on the investigation view. Default 1. Raising it
  re-runs the query at the new depth and **merges** new persons and links
  into the rendered graph rather than replacing it, so the user's existing
  view and camera survive the expansion.
- Confidence rendered as edge thickness/opacity, with a min-confidence
  slider wired to the API param.
- **All detail lands in the right-hand panel**, which already exists: a
  resizable, width-persisting column (`useResizablePanel`, storage key
  `investigation.detailPanelWidth`) that already renders `PropertiesList`
  for a selected person (`InvestigationPage.tsx:479`) and a selected
  attribute (`:510`). Three selection cases feed it, and nothing else:
  - **person selected** — identity fields, plus the list of their documents.
  - **document sub-node selected** — that document's full field set, via
    `PropertiesList` unchanged; the `:510` attribute branch becomes the
    document branch.
  - **link selected** — the explanation: which field matched, what the value
    was, which documents on each side it came from, and the confidence.

  The canvas itself never renders a property list, a tooltip card, or an
  inline expansion. Clicking a person still *reveals its document sub-nodes
  on the canvas* — that is graph structure, not detail — while the fields
  themselves appear only in the panel.

## 7. Testing

- **Scoring** (`test_connection_confidence.py`, new) — pure-function unit
  tests: weight lookup incl. the unknown-key default, `R(n)` at n=2/3/11,
  cross-key penalty, noisy-OR compounding and its bounds, denylist and
  short-value exclusion, identifier vs. text normalisation.
- **Projection** (`test_person_network_service.py`, extend) — two people
  whose separate documents share a `father_name` link at degree 1 with the
  expected confidence; a third person sharing a different value with the
  second appears at degree 2 and not degree 1; `min_confidence` drops weak
  links *and* the persons only reachable through them; a value with 40 owners
  is suppressed as a hub.
- **Ingestion** (`test_normalize.py`, extend) — an Emirates ID becomes its
  own document vertex rather than `person.national_id`; the same passport in
  two files dedupes to one vertex; denylisted and too-short fields emit no
  `field_value` vertex.
- **Frontend** — manual verification via `./dev` (the repo has minimal
  frontend test coverage today): document-only sub-nodes, degree expand-in-
  place, confidence filter.

## 8. Backfill

Already-ingested data in `intel_kg_v2` has no `field_value` vertices and no
generalised documents, and that space persists across runs — so a one-shot
reindex job is required, not optional. It walks existing person and document
vertices, emits `HAS_FIELD_VALUE` edges under the current denylist and
normalisation rules, and converts existing `Passport` vertices and
`person.national_id` attributes into `document` vertices. It must be
re-runnable: rerunning after a weight or denylist change rebuilds the index
without duplicating vertices.

## 9. Out of scope

- **Fuzzy matching.** Exact match on the normalised value only. "Mohammed"
  vs "Mohammad", transliteration variants and typo tolerance are a natural
  follow-up, but they need string-similarity thresholds and a much larger
  candidate-generation story, and they are not needed for the behaviour
  described here.
- Learned or feedback-driven weights — `W` is a hand-tuned table for now.
- Changes to risk scoring, shortest-path, or CSV import.
- Explorer page behaviour, which keeps its current mixed-node view.

## 10. Risks

- **Graph size.** One vertex per distinct field value, plus an edge per
  person-field. Memory is the binding constraint on this box (~1.4GB
  container cap, per CLAUDE.md). The denylist, the 3-character floor and hub
  suppression bound the worst offenders; the backfill job should report
  vertex counts so growth is visible before it becomes a problem.
- **`R(n)` is a proxy**, not a calibrated u-probability. It is monotone and
  bounded, which is enough to rank and filter, but the constants in `W` and
  the 0.6 cross-key penalty are guesses until there is real data to tune
  against. They live in one table for exactly that reason.
- **Cross-key matching is the noisiest part** of the design and the most
  likely thing to want a tighter rule later. Keeping it behind a penalty
  multiplier rather than a hard rule means tightening it is a constant
  change, not a redesign.
