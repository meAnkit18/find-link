# Document-Sourced Person Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Person nodes reveal only their document sub-nodes, and connections between people are inferred from field values matching across those documents, scored by confidence and traversable to degree 3.

**Architecture:** A generic `document` entity type replaces the passport-only special case in the extraction ontology. At write time, every eligible field value on a person or their documents emits a `field_value` connector vertex keyed by the normalised value alone, joined to the person by a `HAS_FIELD_VALUE` edge carrying the field key. Two people on the same `field_value` vertex is structurally identical to two people sharing a phone vertex, so the existing `PersonNetworkService` projection, hub suppression and degree BFS handle traversal unchanged; only scoring is new.

**Tech Stack:** Python 3.11+ / FastAPI / NebulaGraph (via `graph-core`) on the backend; React + TypeScript + Vite on the frontend; pytest for tests.

## Global Constraints

- **Exact matching only.** No fuzzy/string-similarity matching anywhere in this plan. Values match after normalisation or they do not match.
- **No person-to-person edges are materialised.** Connections are derived by the projection at query time from `field_value` connector vertices.
- **Never render `field_value` vertices as graph nodes.** They are an index; they surface only inside link explanations.
- **Denylisted field keys** (never indexed): `nationality`, `gender`, `sex`, `country`, `document_type`, `issuer`, `issuing_authority`, `issuing_country`.
- **Minimum indexed value length is 3 characters**, and a bare 4-digit year is never indexed.
- **Vertex ids must fit `FIXED_STRING(64)`** — the space is created with that vid type (`ingest_schema.py:99`).
- **Confidence is always in `[0.0, 1.0]`.**
- Run tests with `.venv/bin/pytest` from the repo root.
- Do **not** start the stack (`./dev`) without asking — shared box, NebulaGraph is memory-hungry (see `CLAUDE.md`).

**Naming note:** `packages/entity-resolution/` solves a *different* problem — deciding whether two records are the *same* person (dedup, via rapidfuzz/embeddings). This plan infers connections between *different* people. Do not import from or extend `entity_resolution`; do not add fuzzy matching to imitate it.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `packages/intelligence-schema/src/intelligence_schema/field_index.py` | Pure functions: value normalisation, eligibility, `field_value` vid. No graph access. |
| `apps/api/src/graph_explorer_api/services/connection_confidence.py` | Pure functions: field weights, rarity, cross-key penalty, noisy-OR. No graph access. |
| `apps/api/tests/unit/test_field_index.py` | Tests for `field_index`. |
| `apps/api/tests/unit/test_connection_confidence.py` | Tests for `connection_confidence`. |
| `scripts/reindex_field_values.py` | Re-runnable backfill over an existing space. |

**Modified:**

| File | Change |
|---|---|
| `packages/ingestion-core/src/ingestion_core/canonical.py` | `PASSPORT` → `DOCUMENT`; `HAS_PASSPORT` → `HAS_DOCUMENT`. |
| `packages/ingestion-core/src/ingestion_core/normalize.py` | Document branch in `deterministic_key` / `normalize_extraction`. |
| `packages/ingestion-core/src/ingestion_core/extraction.py` | Prompt rule: government IDs become documents. |
| `packages/intelligence-schema/src/intelligence_schema/ingest_schema.py` | `document` tag, `field_value` tag, `HAS_DOCUMENT` + `HAS_FIELD_VALUE` edges. |
| `packages/intelligence-schema/src/intelligence_schema/graph_writer.py` | `upsert_field_value` + `link_field_value`. |
| `packages/evidence-core/src/evidence_core/pipeline.py` | Emit the index during `step_write`. |
| `apps/api/src/graph_explorer_api/services/person_network_service.py` | `HAS_FIELD_VALUE` connector, per-via confidence, `min_confidence`. |
| `apps/api/src/graph_explorer_api/routers/entities.py` | `min_confidence` query param. |
| `apps/web/src/api/types.ts` | `shared_field` via variant; `confidence` on `PersonLink`. |
| `apps/web/src/api/client.ts` | `minConfidence` option. |
| `apps/web/src/hooks/usePersonNetworkState.ts` | Document-only sub-nodes; preserve expansion across degree change. |
| `apps/web/src/pages/InvestigationPage.tsx` | Confidence slider; link detail in the right panel. |
| `apps/web/src/components/explorer/graphStyle.ts` | `edgeConfidence` for edge width. |

---

## Task 1: Generalise the extraction ontology from Passport to Document

**Files:**
- Modify: `packages/ingestion-core/src/ingestion_core/canonical.py:9-35`
- Modify: `packages/ingestion-core/src/ingestion_core/normalize.py:86-89,132-138`
- Test: `apps/api/tests/unit/test_normalize.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `EntityType.DOCUMENT` (value `"Document"`), relationship type `"HAS_DOCUMENT"`, and `deterministic_key` returning `"document:<TYPE>:<NUMBER>"` for document entities.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_normalize.py`:

```python
from ingestion_core.canonical import EntityType, ExtractedEntity, RELATIONSHIP_TYPES
from ingestion_core.normalize import deterministic_key


def _doc(number: str, document_type: str) -> ExtractedEntity:
    return ExtractedEntity(
        local_id="e1",
        type=EntityType.DOCUMENT,
        name=number,
        attributes={"number": number, "document_type": document_type},
        confidence=0.9,
    )


def test_document_is_an_entity_type():
    assert EntityType.DOCUMENT.value == "Document"
    assert not hasattr(EntityType, "PASSPORT")


def test_has_document_replaces_has_passport():
    assert "HAS_PASSPORT" not in RELATIONSHIP_TYPES
    assert RELATIONSHIP_TYPES["HAS_DOCUMENT"] == ({"Person"}, {"Document"})


def test_deterministic_key_separates_document_types():
    """An Emirates ID and a passport that happen to share a number are two
    different documents, so the key includes the type."""
    assert (
        deterministic_key(_doc("784-1990-1234567-1", "emirates_id"))
        == "document:EMIRATES_ID:784199012345671"
    )
    assert deterministic_key(_doc("P1234567", "passport")) == "document:PASSPORT:P1234567"
    assert deterministic_key(_doc("X1", "passport")) != deterministic_key(_doc("X1", "emirates_id"))


def test_deterministic_key_ignores_document_number_separators():
    with_seps = deterministic_key(_doc("P-123 4567", "passport"))
    without = deterministic_key(_doc("P1234567", "passport"))
    assert with_seps == without


def test_document_without_type_defaults_to_document():
    entity = ExtractedEntity(
        local_id="e1", type=EntityType.DOCUMENT, name="P1234567",
        attributes={"number": "P1234567"}, confidence=0.9,
    )
    assert deterministic_key(entity) == "document:DOCUMENT:P1234567"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_normalize.py -v`
Expected: FAIL — `AttributeError: DOCUMENT` / `ImportError`.

- [ ] **Step 3: Change the ontology**

In `canonical.py`, replace the `PASSPORT` member and the `HAS_PASSPORT` entry:

```python
class EntityType(str, Enum):
    PERSON = "Person"
    COMPANY = "Company"
    ORGANIZATION = "Organization"
    ADDRESS = "Address"
    COUNTRY = "Country"
    DOCUMENT = "Document"
    PHONE = "Phone"
    EMAIL = "Email"
    BANK_ACCOUNT = "BankAccount"
    VEHICLE = "Vehicle"
```

and in `RELATIONSHIP_TYPES` replace the `"HAS_PASSPORT"` line with:

```python
    "HAS_DOCUMENT": ({"Person"}, {"Document"}),
```

- [ ] **Step 4: Change normalisation**

In `normalize.py`, replace the `Passport` branch of `deterministic_key` (lines 86-89) with:

```python
    if t == "Document":
        raw = attrs.get("number") or entity.name
        v = normalize_national_id(str(raw))
        doc_type = str(attrs.get("document_type") or "document").strip().upper()
        return f"document:{doc_type}:{v}" if v else None
```

and replace the `Passport` branch of `normalize_extraction` (lines 132-138) with:

```python
        elif t == "Document":
            raw = attrs.get("number") or ent.name
            attrs["number"] = normalize_national_id(str(raw))
            ent.name = attrs["number"]
            attrs["document_type"] = str(attrs.get("document_type") or "document").strip().lower()
            for k in ("issue_date", "expiry_date", "dob"):
                if k in attrs and (norm := normalize_date(str(attrs[k]))):
                    attrs[k] = norm
```

`normalize_national_id` and `normalize_passport_number` are identical implementations; the document branch uses `normalize_national_id` so one helper covers every document type.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/test_normalize.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/ingestion-core/src/ingestion_core/canonical.py \
        packages/ingestion-core/src/ingestion_core/normalize.py \
        apps/api/tests/unit/test_normalize.py
git commit -m "feat(ingestion): generalise Passport into a Document entity type"
```

---

## Task 2: Teach the extractor that government IDs are documents

**Files:**
- Modify: `packages/ingestion-core/src/ingestion_core/extraction.py:29-36`

**Interfaces:**
- Consumes: `EntityType.DOCUMENT` from Task 1 (the prompt's `ENTITY_TYPES` list is generated from the enum, so it updates itself).
- Produces: extractions that carry `Document` entities with `attributes.document_type`.

- [ ] **Step 1: Replace the prompt rule**

In `extraction.py`, replace these lines:

```
- A person's government-issued ID number (Emirates ID, national ID, SSN, ...)
  goes in attributes.national_id — NOT as a separate entity. (Passport
  numbers are the one exception: they get their own Passport entity plus a
  HAS_PASSPORT relationship.)
```

with:

```
- Every identity document (passport, Emirates ID, national ID card, driving
  licence, residence permit, ...) is its own Document entity plus a
  HAS_DOCUMENT relationship from the person. Set attributes.document_type to
  a lowercase snake_case kind ("passport", "emirates_id", "national_id",
  "driving_licence"), attributes.number to the document number, and put every
  other field the document states (father_name, mother_name, place_of_birth,
  issue_date, expiry_date, dob, address, ...) in that Document's attributes —
  NOT on the person.
- The person keeps only their own identity fields (name, dob). Do not copy a
  document's fields onto the person.
```

- [ ] **Step 2: Verify the prompt renders with the new ontology**

Run:

```bash
.venv/bin/python -c "
from ingestion_core.extraction import SYSTEM_PROMPT
assert 'Document' in SYSTEM_PROMPT, 'Document missing from entity types'
assert 'HAS_DOCUMENT' in SYSTEM_PROMPT, 'HAS_DOCUMENT missing from relationship types'
assert 'Passport' not in SYSTEM_PROMPT, 'stale Passport reference remains'
assert 'HAS_PASSPORT' not in SYSTEM_PROMPT, 'stale HAS_PASSPORT reference remains'
print('prompt OK')
"
```

Expected: `prompt OK`

- [ ] **Step 3: Commit**

```bash
git add packages/ingestion-core/src/ingestion_core/extraction.py
git commit -m "feat(ingestion): extract every identity document as a Document entity"
```

---

## Task 3: The field-value index primitives

**Files:**
- Create: `packages/intelligence-schema/src/intelligence_schema/field_index.py`
- Test: `apps/api/tests/unit/test_field_index.py`

**Interfaces:**
- Consumes: nothing (pure module, no graph access).
- Produces:
  - `DENYLISTED_KEYS: frozenset[str]`
  - `normalize_value(raw: object) -> str | None`
  - `is_eligible(field_key: str, normalized: str | None) -> bool`
  - `value_vid(normalized: str) -> str`
  - `field_values(props: dict) -> list[tuple[str, str]]` — sorted, deduped `(field_key, normalized_value)` pairs.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/test_field_index.py`:

```python
"""Field-index primitives: what gets indexed, and under which vertex id."""

from __future__ import annotations

from intelligence_schema.field_index import (
    field_values,
    is_eligible,
    normalize_value,
    value_vid,
)


def test_normalize_casefolds_and_collapses_whitespace():
    assert normalize_value("  Ahmed   Al-Mansouri ") == "ahmed al-mansouri"


def test_identifier_values_lose_their_separators():
    """784-1990-1234567-1 and 784 1990 1234567 1 are one value."""
    assert normalize_value("784-1990-1234567-1") == normalize_value("784 1990 1234567 1")
    assert normalize_value("784-1990-1234567-1") == "784199012345671"


def test_text_values_keep_their_hyphens():
    """Only values containing a digit are treated as identifiers."""
    assert normalize_value("Al-Mansouri") == "al-mansouri"


def test_blank_and_none_normalize_to_none():
    assert normalize_value(None) is None
    assert normalize_value("   ") is None


def test_denylisted_keys_are_never_eligible():
    for key in ("nationality", "Gender", "COUNTRY", "document_type", "issuing_authority"):
        assert is_eligible(key, "anything") is False


def test_short_values_and_bare_years_are_not_eligible():
    assert is_eligible("father_name", "ab") is False
    assert is_eligible("issue_year", "1990") is False
    assert is_eligible("father_name", None) is False


def test_ordinary_field_is_eligible():
    assert is_eligible("father_name", "ahmed al-mansouri") is True


def test_value_vid_is_stable_short_and_value_only():
    vid = value_vid("ahmed al-mansouri")
    assert vid == value_vid("ahmed al-mansouri")
    assert vid.startswith("value:")
    assert len(vid) <= 64
    assert vid != value_vid("ahmed al-mansour")


def test_field_values_filters_and_sorts():
    props = {
        "father_name": "Ahmed Al-Mansouri",
        "nationality": "UAE",          # denylisted
        "gender": "M",                 # denylisted
        "number": "P-123 4567",
        "issue_year": "1990",          # bare year
        "aliases": ["x", "y"],         # non-scalar
        "empty": "",
    }
    assert field_values(props) == [
        ("father_name", "ahmed al-mansouri"),
        ("number", "p1234567"),
    ]


def test_field_values_tolerates_empty_input():
    assert field_values({}) == []
    assert field_values(None) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_field_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'intelligence_schema.field_index'`

- [ ] **Step 3: Write the implementation**

Create `packages/intelligence-schema/src/intelligence_schema/field_index.py`:

```python
"""Which field values are worth indexing, and under what vertex id.

Two people are connected when their documents agree on a value. To find that
without scanning every document, each eligible value becomes a `field_value`
vertex that both people attach to — so "agreeing on a value" is stored as
"attached to the same vertex", which the person projection already knows how
to walk.

The vertex is keyed by the *normalised value alone*, never by (key, value).
That is deliberate: it lets a value stored under `father_name` on one
document match the same value stored under `guarantor_name` on another. Which
key each side used lives on the edge, so the projection can still tell a
same-key match from a cross-key one and score them differently.
"""

from __future__ import annotations

import hashlib
import re

# Fields that agree constantly by coincidence. Indexing them would connect
# every UAE national to every other one and drown the real leads.
DENYLISTED_KEYS = frozenset({
    "nationality",
    "gender",
    "sex",
    "country",
    "document_type",
    "issuer",
    "issuing_authority",
    "issuing_country",
})

MIN_VALUE_LENGTH = 3

_WHITESPACE = re.compile(r"\s+")
_SEPARATORS = re.compile(r"[\s\-/.]")
_BARE_YEAR = re.compile(r"^\d{4}$")


def normalize_value(raw: object) -> str | None:
    """The form a value is indexed under, or None if it is not indexable.

    Values containing a digit are treated as identifiers and lose their
    separators, so `784-1990-1234567-1` and `784 1990 1234567 1` land on one
    vertex. Text keeps its punctuation — stripping hyphens from names would
    be harmless but pointless, and keeping them makes the stored value
    readable in a link explanation.
    """
    if raw is None:
        return None
    text = _WHITESPACE.sub(" ", str(raw)).strip().casefold()
    if not text:
        return None
    if any(ch.isdigit() for ch in text):
        text = _SEPARATORS.sub("", text)
    return text or None


def is_eligible(field_key: str, normalized: str | None) -> bool:
    """Whether this (key, normalised value) should enter the index."""
    if field_key.strip().casefold() in DENYLISTED_KEYS:
        return False
    if not normalized or len(normalized) < MIN_VALUE_LENGTH:
        return False
    if _BARE_YEAR.match(normalized):
        return False
    return True


def value_vid(normalized: str) -> str:
    """Vertex id for a normalised value. Hashed because the value itself can
    exceed the space's FIXED_STRING(64) vid width."""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:32]
    return f"value:{digest}"


def field_values(props: dict | None) -> list[tuple[str, str]]:
    """Every indexable (field_key, normalised value) in a property bag.

    Non-scalar values (lists such as `aliases`, nested dicts) are skipped —
    they have no single value to match on.
    """
    found: set[tuple[str, str]] = set()
    for key, raw in (props or {}).items():
        if isinstance(raw, (dict, list, tuple, set)):
            continue
        normalized = normalize_value(raw)
        if is_eligible(str(key), normalized):
            found.add((str(key), normalized))
    return sorted(found)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/test_field_index.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/intelligence-schema/src/intelligence_schema/field_index.py \
        apps/api/tests/unit/test_field_index.py
git commit -m "feat(schema): add field-value index primitives"
```

---

## Task 4: Graph schema for documents and the field-value index

**Files:**
- Modify: `packages/intelligence-schema/src/intelligence_schema/ingest_schema.py:30-57,102-125`

**Interfaces:**
- Consumes: nothing.
- Produces: the `document` and `field_value` tags and the `HAS_DOCUMENT` / `HAS_FIELD_VALUE` edge types, created by `ensure_ingest_schema`.

- [ ] **Step 1: Update the tag and edge maps**

In `ingest_schema.py`, in `ENTITY_TAG` replace `"Passport": "passport",` with:

```python
    "Document": "document",
```

In `KEY_COLUMN` replace `"passport": "number",` with:

```python
    "document": "number",
```

In `INGEST_EDGE_TYPES` replace `"HAS_PASSPORT"` with `"HAS_DOCUMENT"`, giving:

```python
INGEST_EDGE_TYPES: list[str] = [
    "WORKS_AT", "OWNS", "PAYS", "HAS_DOCUMENT", "HAS_PHONE", "HAS_EMAIL",
    "HAS_ACCOUNT", "OWNS_VEHICLE", "LOCATED_AT", "CITIZEN_OF", "RELATED_TO",
]
```

- [ ] **Step 2: Create the `field_value` tag and its edge**

In `ensure_ingest_schema`, immediately after the `evidence` tag creation block (which ends with the `create_tag(TagSchema(name="evidence", ...))` call around line 111-118), add:

```python
        # The field-value index. `value` is the normalised value itself, kept
        # readable so a link explanation can say what actually matched.
        client.metadata.create_tag(TagSchema(name="field_value", properties=[
            PropertyDefinition("label", "string"),
            PropertyDefinition("entity_type", "string"),
            PropertyDefinition("value", "string", nullable=True),
            PropertyDefinition("created_at", "int64", nullable=True),
        ]))
```

and immediately after the `SUPPORTED_BY` edge creation block (around line 123-126), add:

```python
        # person -> field_value. `field_key` is which field on that person's
        # document held the value, and is what separates a same-key match
        # from a cross-key one when the projection scores the link.
        client.metadata.create_edge_type(EdgeSchema(name="HAS_FIELD_VALUE", properties=[
            PropertyDefinition("field_key", "string", nullable=True),
            PropertyDefinition("document_id", "string", nullable=True),
            PropertyDefinition("document_type", "string", nullable=True),
            PropertyDefinition("created_at", "int64", nullable=True),
        ]))
```

- [ ] **Step 3: Verify the schema module is consistent**

Run:

```bash
.venv/bin/python -c "
from intelligence_schema.ingest_schema import ENTITY_TAG, KEY_COLUMN, INGEST_EDGE_TYPES
assert ENTITY_TAG['Document'] == 'document'
assert 'Passport' not in ENTITY_TAG
assert KEY_COLUMN['document'] == 'number'
assert 'HAS_DOCUMENT' in INGEST_EDGE_TYPES and 'HAS_PASSPORT' not in INGEST_EDGE_TYPES
print('schema maps OK')
"
```

Expected: `schema maps OK`

- [ ] **Step 4: Commit**

```bash
git add packages/intelligence-schema/src/intelligence_schema/ingest_schema.py
git commit -m "feat(schema): add document tag and the field_value index schema"
```

---

## Task 5: Write the field-value index during ingestion

**Files:**
- Modify: `packages/intelligence-schema/src/intelligence_schema/graph_writer.py` (add two methods after `link_supported_by`, around line 106)
- Modify: `packages/evidence-core/src/evidence_core/pipeline.py:465-479` (inside `step_write`)

**Interfaces:**
- Consumes: `field_values`, `value_vid` (Task 3); `HAS_FIELD_VALUE` schema (Task 4).
- Produces: `GraphWriter.index_field_values(owner_vid, props, document_id=None, document_type=None) -> int`, returning how many values it indexed.

- [ ] **Step 1: Add the writer method**

In `graph_writer.py`, add this import at the top:

```python
from intelligence_schema.field_index import field_values, value_vid
```

and add these methods to `GraphWriter`, immediately after `link_supported_by`:

```python
    # ------------------------------------------------------- field index

    def index_field_values(
        self, owner_vid: str, props: dict[str, Any] | None,
        document_id: str | None = None, document_type: str | None = None,
    ) -> int:
        """Index a property bag's values against the person who holds them.

        Values are attached to the *person*, not the document, so two people
        who agree on a value are two hops apart — the same shape as two
        people sharing a phone, which the projection already walks. The
        originating document rides along on the edge so an explanation can
        still name it.

        Returns the number of values indexed.
        """
        pairs = field_values(props)
        now = int(time.time())
        for field_key, normalized in pairs:
            vid = value_vid(normalized)
            self._client.execute_raw(
                f'INSERT VERTEX field_value(label, entity_type, value, created_at) '
                f'VALUES {self._ngql_value(vid)}:('
                f'{self._ngql_value(normalized)}, {self._ngql_value("field_value")}, '
                f'{self._ngql_value(normalized)}, {now});'
            )
            self._client.execute_raw(
                f'INSERT EDGE HAS_FIELD_VALUE('
                f'field_key, document_id, document_type, created_at) VALUES '
                f'{self._ngql_value(str(owner_vid))}->{self._ngql_value(vid)}:('
                f'{self._ngql_value(field_key)}, {self._ngql_value(document_id or "")}, '
                f'{self._ngql_value(document_type or "")}, {now});'
            )
        return len(pairs)
```

- [ ] **Step 2: Call it from the write step**

In `pipeline.py`'s `step_write`, the entity loop currently ends with `entities_written += 1`. Replace the body of that `if reg:` block so the index is written alongside the entity:

```python
            if reg:
                attributes = {**(reg.attributes or {}), "aliases": reg.aliases or []}
                writer.upsert_entity(
                    tag=reg.type,
                    vid=reg.id,
                    name=reg.canonical_name,
                    attributes=attributes,
                    confidence=reg.confidence,
                    evidence_id=evidence_id,
                )
                writer.link_supported_by(reg.id, evidence_id, fact.confidence)
                if reg.type == "Person":
                    writer.index_field_values(reg.id, attributes)
                entities_written += 1
                fact.status = "written"
                db.add(fact)
```

Then, after the relationship loop completes (immediately before `ev.status = "written"`), add the document pass — a document's fields are indexed against every person holding that document, which is what makes two people's *separate* documents comparable:

```python
        # A document's fields belong, for matching purposes, to the person who
        # holds it: indexing them against the person is what lets two people's
        # separate documents be compared without a four-hop traversal.
        for fact in (f for f in facts if f.kind == "relationship"):
            if fact.payload.get("type") != "HAS_DOCUMENT":
                continue
            document = db.get(EntityRegistry, fact.resolved_target_id)
            if document is None:
                continue
            attributes = document.attributes or {}
            writer.index_field_values(
                fact.resolved_source_id,
                attributes,
                document_id=document.id,
                document_type=str(attributes.get("document_type") or "document"),
            )
```

- [ ] **Step 3: Verify the writer emits the expected nGQL**

Run:

```bash
.venv/bin/python -c "
from intelligence_schema.graph_writer import GraphWriter

class FakeClient:
    def __init__(self): self.statements = []
    def execute_raw(self, ngql): self.statements.append(ngql)

client = FakeClient()
count = GraphWriter(client).index_field_values(
    'person:1',
    {'father_name': 'Ahmed Al-Mansouri', 'nationality': 'UAE', 'number': 'P-123 4567'},
    document_id='doc:1', document_type='passport',
)
assert count == 2, count
vertices = [s for s in client.statements if s.startswith('INSERT VERTEX')]
edges = [s for s in client.statements if s.startswith('INSERT EDGE')]
assert len(vertices) == 2 and len(edges) == 2
assert all('field_value' in s for s in vertices)
assert all('HAS_FIELD_VALUE' in s and 'person:1' in s for s in edges)
assert not any('UAE' in s or 'uae' in s for s in client.statements), 'denylisted key leaked'
assert any('\"father_name\"' in s for s in edges)
assert any('p1234567' in s for s in vertices), 'identifier not normalised'
print('writer OK')
"
```

Expected: `writer OK`

- [ ] **Step 4: Commit**

```bash
git add packages/intelligence-schema/src/intelligence_schema/graph_writer.py \
        packages/evidence-core/src/evidence_core/pipeline.py
git commit -m "feat(ingestion): index document field values against their holder"
```

---

## Task 6: Connection confidence scoring

**Files:**
- Create: `apps/api/src/graph_explorer_api/services/connection_confidence.py`
- Test: `apps/api/tests/unit/test_connection_confidence.py`

**Interfaces:**
- Consumes: nothing (pure module).
- Produces:
  - `WEIGHTS: dict[str, float]`, `DEFAULT_WEIGHT: float`, `CROSS_KEY_PENALTY: float`
  - `DIRECT_CONFIDENCE: float`, `BRIDGE_CONFIDENCE: float`
  - `weight_for(key: str) -> float`
  - `rarity(owner_count: int) -> float`
  - `match_confidence(key: str, owner_count: int, same_key: bool) -> float`
  - `combine(confidences: Iterable[float]) -> float`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/test_connection_confidence.py`:

```python
"""Scoring an inferred connection.

A field's worth is how unlikely it is to agree by chance — a near-unique
identifier is strong evidence, a value forty people share is not.
"""

from __future__ import annotations

import pytest

from graph_explorer_api.services.connection_confidence import (
    CROSS_KEY_PENALTY,
    DEFAULT_WEIGHT,
    combine,
    match_confidence,
    rarity,
    weight_for,
)


def test_identifier_fields_outweigh_soft_fields():
    assert weight_for("passport_number") > weight_for("father_name")
    assert weight_for("father_name") > weight_for("company")


def test_weight_lookup_is_case_insensitive():
    assert weight_for("Father_Name") == weight_for("father_name")


def test_unknown_keys_get_the_default_weight():
    """An unanticipated field still forms connections — that's the point."""
    assert weight_for("grandfather_maiden_name") == DEFAULT_WEIGHT


def test_rarity_falls_as_more_people_share_a_value():
    assert rarity(2) == 1.0
    assert rarity(3) == 0.5
    assert rarity(11) == pytest.approx(0.1)


def test_rarity_of_an_unshared_value_is_zero():
    """One owner links nobody."""
    assert rarity(1) == 0.0
    assert rarity(0) == 0.0


def test_cross_key_matches_are_penalised():
    same = match_confidence("father_name", 2, same_key=True)
    cross = match_confidence("father_name", 2, same_key=False)
    assert cross == pytest.approx(same * CROSS_KEY_PENALTY)
    assert cross < same


def test_common_value_scores_near_zero_even_for_a_strong_field():
    assert match_confidence("passport_number", 200, same_key=True) < 0.01


def test_confidence_stays_within_bounds():
    for count in (1, 2, 3, 50):
        for same in (True, False):
            assert 0.0 <= match_confidence("passport_number", count, same) <= 1.0


def test_combine_compounds_independent_matches():
    """Two medium signals beat either alone — noisy-OR, not max."""
    combined = combine([0.5, 0.5])
    assert combined == pytest.approx(0.75)
    assert combined > 0.5


def test_combine_of_one_is_itself():
    assert combine([0.42]) == pytest.approx(0.42)


def test_combine_of_nothing_is_zero():
    assert combine([]) == 0.0


def test_combine_never_exceeds_one():
    assert combine([0.9, 0.9, 0.9, 0.9]) <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_connection_confidence.py -v`
Expected: FAIL — `ModuleNotFoundError: ... connection_confidence`

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/graph_explorer_api/services/connection_confidence.py`:

```python
"""How much a shared value is worth as evidence of a connection.

Follows the Fellegi-Sunter shape: a field's weight is how unlikely it is to
agree by chance. A passport number two people share is near-conclusive; a
value forty people share is noise regardless of which field it sits in. The
constants below are hand-tuned starting points, deliberately gathered in one
table because they will want retuning against real data.
"""

from __future__ import annotations

from collections.abc import Iterable

# Keyed by document field key *or* by connector tag — a shared `document`
# vertex and a matching `passport_number` field are both scored from here.
WEIGHTS: dict[str, float] = {
    # Near-unique identifiers.
    "passport_number": 0.95,
    "national_id": 0.95,
    "emirates_id": 0.95,
    "number": 0.95,
    "iban": 0.95,
    "document": 0.95,
    "bank_account": 0.9,
    # Strong but not unique.
    "phone": 0.8,
    "email": 0.8,
    "vehicle": 0.8,
    "father_name": 0.7,
    "mother_name": 0.7,
    "address": 0.7,
    "dob": 0.7,
    "place_of_birth": 0.7,
    # Real leads, but plenty of people share them.
    "company": 0.4,
    "organization": 0.4,
}

# An unanticipated field still forms connections — a fixed allowlist is
# exactly what this design set out to avoid.
DEFAULT_WEIGHT = 0.5

# A value matching across *different* field keys is a weaker claim than the
# same field agreeing on both sides, but not a worthless one.
CROSS_KEY_PENALTY = 0.6

# A stored person-to-person relationship is an assertion, not an inference.
DIRECT_CONFIDENCE = 0.9

# Two people at different-but-related organisations: a real lead, a weak one.
BRIDGE_CONFIDENCE = 0.4


def weight_for(key: str) -> float:
    return WEIGHTS.get(key.strip().casefold(), DEFAULT_WEIGHT)


def rarity(owner_count: int) -> float:
    """How much a value's scarcity vouches for it.

    Two owners and nobody else scores 1.0; the value falls away as the
    crowd grows. Fewer than two owners links nobody, so it scores 0.
    """
    if owner_count < 2:
        return 0.0
    return 1.0 / (owner_count - 1)


def match_confidence(key: str, owner_count: int, same_key: bool) -> float:
    """Confidence contributed by one matching value."""
    score = weight_for(key) * rarity(owner_count) * (1.0 if same_key else CROSS_KEY_PENALTY)
    return min(1.0, max(0.0, score))


def combine(confidences: Iterable[float]) -> float:
    """Noisy-OR across independent matches.

    Two people sharing a father's name *and* an address are more connected
    than either fact alone implies, so the reasons compound rather than the
    pair being scored by its single best one.
    """
    remaining = 1.0
    for confidence in confidences:
        remaining *= 1.0 - min(1.0, max(0.0, confidence))
    return 1.0 - remaining
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/test_connection_confidence.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/graph_explorer_api/services/connection_confidence.py \
        apps/api/tests/unit/test_connection_confidence.py
git commit -m "feat(api): add connection confidence scoring"
```

---

## Task 7: Project field-value matches into person links

**Files:**
- Modify: `apps/api/src/graph_explorer_api/services/person_network_service.py:38-47,314-364,563-574`
- Test: `apps/api/tests/unit/test_person_network_service.py`

**Interfaces:**
- Consumes: `match_confidence`, `combine`, `DIRECT_CONFIDENCE`, `BRIDGE_CONFIDENCE` (Task 6).
- Produces: a `shared_field` via kind; every via carries a `confidence` float; every finalized link carries a `confidence` float.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_person_network_service.py`:

```python
FIELD_VALUE = "HAS_FIELD_VALUE"


def value_node(value: str) -> dict:
    return {"field_value": {"label": value, "entity_type": "field_value"}}


@pytest.fixture
def shared_father_name():
    """A and B have separate passports naming the same father."""
    return make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:father": value_node("ahmed al-mansouri"),
        },
        [
            ("a", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
        ],
    )


def test_matching_field_links_two_people(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    assert set(ids(network)) == {"a", "b"}
    assert link_pairs(network) == {("a", "b")}


def test_matching_field_link_reports_why(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    via = network["links"][0]["via"][0]
    assert via["kind"] == "shared_field"
    assert via["field_key"] == "father_name"
    assert via["same_key"] is True
    assert via["connector_label"] == "ahmed al-mansouri"


def test_same_key_match_on_a_rare_value_is_confident(shared_father_name):
    network = shared_father_name.person_network("a", degree=1)
    # weight_for("father_name") == 0.7, rarity(2) == 1.0, same key
    assert network["links"][0]["confidence"] == pytest.approx(0.7)


def test_cross_key_match_is_penalised():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:x": value_node("12 main st"),
        },
        [
            ("a", "value:x", FIELD_VALUE, {"field_key": "address"}),
            ("b", "value:x", FIELD_VALUE, {"field_key": "employer_address"}),
        ],
    )
    network = service.person_network("a", degree=1)
    via = network["links"][0]["via"][0]
    assert via["same_key"] is False
    # 0.7 * 1.0 * 0.6
    assert network["links"][0]["confidence"] == pytest.approx(0.42)


def test_two_matching_fields_compound():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "value:father": value_node("ahmed"),
            "value:addr": value_node("12 main st"),
        },
        [
            ("a", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:father", FIELD_VALUE, {"field_key": "father_name"}),
            ("a", "value:addr", FIELD_VALUE, {"field_key": "address"}),
            ("b", "value:addr", FIELD_VALUE, {"field_key": "address"}),
        ],
    )
    network = service.person_network("a", degree=1)
    link = network["links"][0]
    assert len(link["via"]) == 2
    # noisy-OR of 0.7 and 0.7
    assert link["confidence"] == pytest.approx(0.91)


def test_a_value_shared_by_a_crowd_scores_low():
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    service = make_service(
        {**people, "value:x": value_node("dubai")},
        [(f"p{i}", "value:x", FIELD_VALUE, {"field_key": "city"}) for i in range(6)],
    )
    network = service.person_network("p0", degree=1)
    # rarity(6) == 0.2, default weight 0.5 -> 0.1
    assert network["links"][0]["confidence"] == pytest.approx(0.1)


def test_field_values_chain_into_second_degree():
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "value:1": value_node("ahmed"),
            "value:2": value_node("12 main st"),
        },
        [
            ("a", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
            ("b", "value:2", FIELD_VALUE, {"field_key": "address"}),
            ("c", "value:2", FIELD_VALUE, {"field_key": "address"}),
        ],
    )
    assert degrees(service.person_network("a", degree=2)) == {"a": 0, "b": 1, "c": 2}
    assert "c" not in ids(service.person_network("a", degree=1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_person_network_service.py -v -k "field or father or cross_key or crowd"`
Expected: FAIL — links are empty because `HAS_FIELD_VALUE` is not a connector yet.

- [ ] **Step 3: Register the new connector**

In `person_network_service.py`, add the import:

```python
from graph_explorer_api.services.connection_confidence import (
    BRIDGE_CONFIDENCE,
    DIRECT_CONFIDENCE,
    combine,
    match_confidence,
)
```

and add the tag/edge constants next to `PERSON_TAG`:

```python
FIELD_VALUE_TAG = "field_value"
FIELD_VALUE_EDGE = "HAS_FIELD_VALUE"
```

Then update `SHARED_EDGES` — `HAS_PASSPORT` becomes `HAS_DOCUMENT` (Task 1), and the index edge joins it:

```python
SHARED_EDGES: tuple[str, ...] = (
    "HAS_FIELD_VALUE",
    "HAS_PHONE",
    "HAS_EMAIL",
    "HAS_DOCUMENT",
    "HAS_ACCOUNT",
    "OWNS_VEHICLE",
    "LOCATED_AT",
    "WORKS_AT",
    "OWNS",
)
```

- [ ] **Step 4: Capture field keys and score each via**

In `_expand_level`, the loop that fills `owners` currently records only edge types. Replace it with one that also records which field key each person used:

```python
        connector_set = set(connector_ids)
        owners: dict[str, set[str]] = defaultdict(set)
        owner_edge_types: dict[tuple[str, str], set[str]] = defaultdict(set)
        owner_field_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
        for edge in owners_edges:
            for connector, person in ((edge.src, edge.dst), (edge.dst, edge.src)):
                if connector in connector_set and is_person(person):
                    owners[connector].add(person)
                    owner_edge_types[(connector, person)].add(edge.edge_type)
                    if edge.edge_type == FIELD_VALUE_EDGE:
                        field_key = str(edge.properties.get("field_key") or "").strip()
                        if field_key:
                            owner_field_keys[(connector, person)].add(field_key)
```

In the `for connector, connected in owners.items():` loop, insert a `field_value` branch immediately after the `if len(connected) < 2: continue` guard and before `members = sorted(connected)`:

```python
            members = sorted(connected)

            if _primary_tag(vertex) == FIELD_VALUE_TAG:
                # Unlike a shared phone, a matching value is scored per pair:
                # which field each side used decides whether this is a
                # same-key match or the weaker cross-key kind.
                for index, first in enumerate(members):
                    for second in members[index + 1 :]:
                        first_keys = owner_field_keys[(connector, first)]
                        second_keys = owner_field_keys[(connector, second)]
                        shared_keys = first_keys & second_keys
                        all_keys = sorted(first_keys | second_keys)
                        same_key = bool(shared_keys)
                        field_key = sorted(shared_keys)[0] if same_key else (
                            all_keys[0] if all_keys else ""
                        )
                        result.links[_pair(first, second)].append({
                            "kind": "shared_field",
                            "connector_id": connector,
                            "connector_tag": FIELD_VALUE_TAG,
                            "connector_label": _label_of(vertex, connector),
                            "field_key": field_key,
                            "field_keys": all_keys,
                            "same_key": same_key,
                            "edge_types": [FIELD_VALUE_EDGE],
                            "confidence": match_confidence(field_key, len(connected), same_key),
                        })
                for member in members:
                    if member not in frontier_set and member in vertices:
                        result.persons[member] = vertices[member]
                continue
```

Then remove the now-duplicated `members = sorted(connected)` line that followed, and add a confidence to the existing shared-attribute `via` dict:

```python
            via = {
                "kind": "shared_attribute",
                "connector_id": connector,
                "connector_tag": _primary_tag(vertex),
                "connector_label": _label_of(vertex, connector),
                "edge_types": sorted(
                    {
                        edge_type
                        for member in members
                        for edge_type in owner_edge_types[(connector, member)]
                    }
                ),
                "confidence": match_confidence(
                    _primary_tag(vertex), len(connected), same_key=True
                ),
            }
```

- [ ] **Step 5: Score the other two via kinds**

In `_expand_level`, add `"confidence": DIRECT_CONFIDENCE,` to the `direct` via dict (the one with `"kind": "direct"`). In `_add_bridged_links`, add `"confidence": BRIDGE_CONFIDENCE,` to the `linked_organisation` via dict. Every via kind now carries a confidence, so the link-level calculation is uniform.

- [ ] **Step 6: Put confidence on the finalized link**

Replace `_finalize_link` with:

```python
def _link_confidence(via: list[dict]) -> float:
    """Independent reasons compound — see connection_confidence.combine."""
    return combine(float(entry.get("confidence") or 0.0) for entry in via)


def _finalize_link(link: dict) -> dict:
    via = link["via"]
    if len(via) == 1:
        entry = via[0]
        if entry["kind"] == "shared_attribute":
            label = f"shared {_humanize(entry['connector_tag'])}"
        elif entry["kind"] == "shared_field":
            label = f"matching {_humanize(entry['field_key'] or 'field')}"
        else:
            # direct and linked_organisation both carry a ready sentence
            label = entry["label"]
    else:
        label = f"{len(via)} connections"
    return {**link, "label": label, "confidence": round(_link_confidence(via), 4)}
```

Also extend `_via_key` so two `shared_field` reasons through the same value but different keys stay distinct:

```python
def _via_key(via: dict) -> tuple:
    """Identity of a reason, independent of which end it was found from.

    A bridge discovered walking Priya->Meridian->Nimbus->Arjun and the same
    bridge rediscovered next level as Arjun->Nimbus->Meridian->Priya are one
    reason, not two, so the pair of connectors is sorted rather than ordered.
    """
    connectors = tuple(sorted(c for c in (via.get("connector_id"), via.get("linked_id")) if c))
    return (
        via.get("kind"),
        connectors,
        tuple(via.get("edge_types", [])),
        tuple(via.get("field_keys", [])),
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/test_person_network_service.py -v`
Expected: PASS — the new tests and every pre-existing projection test.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/graph_explorer_api/services/person_network_service.py \
        apps/api/tests/unit/test_person_network_service.py
git commit -m "feat(api): infer person links from matching document field values"
```

---

## Task 8: Filter the network by confidence

**Files:**
- Modify: `apps/api/src/graph_explorer_api/services/person_network_service.py:99-175`
- Modify: `apps/api/src/graph_explorer_api/routers/entities.py:65-89`
- Test: `apps/api/tests/unit/test_person_network_service.py`

**Interfaces:**
- Consumes: `_link_confidence` (Task 7).
- Produces: `person_network(..., min_confidence: float = 0.0)`; the `min_confidence` query parameter on `GET /api/entities/{id}/person-network`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_person_network_service.py`:

```python
@pytest.fixture
def weak_then_strong():
    """A-B is a weak city match; B-C is a strong passport-number match."""
    people = {f"p{i}": person(f"P{i}") for i in range(6)}
    return make_service(
        {
            **people,
            "a": person("Alice"),
            "value:city": value_node("dubai"),
            "value:pp": value_node("p1234567"),
        },
        [
            ("a", "value:city", FIELD_VALUE, {"field_key": "city"}),
            *[(f"p{i}", "value:city", FIELD_VALUE, {"field_key": "city"}) for i in range(6)],
            ("p0", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
        ],
    )


def test_weak_links_survive_a_zero_threshold(weak_then_strong):
    network = weak_then_strong.person_network("a", degree=1, min_confidence=0.0)
    assert ("a", "p0") in link_pairs(network)


def test_min_confidence_drops_weak_links(weak_then_strong):
    network = weak_then_strong.person_network("a", degree=1, min_confidence=0.5)
    assert link_pairs(network) == set()


def test_a_dropped_link_is_not_a_stepping_stone(weak_then_strong):
    """A confidence filter has to cut the path, not just hide one edge."""
    network = weak_then_strong.person_network("a", degree=2, min_confidence=0.5)
    assert ids(network) == ["a"]


def test_min_confidence_keeps_strong_links(shared_father_name):
    network = shared_father_name.person_network("a", degree=1, min_confidence=0.5)
    assert link_pairs(network) == {("a", "b")}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_person_network_service.py -v -k confidence`
Expected: FAIL — `TypeError: person_network() got an unexpected keyword argument 'min_confidence'`

- [ ] **Step 3: Add the parameter and filter**

In `person_network`, add the parameter to the signature (after `degree`):

```python
    def person_network(
        self,
        root_id: str,
        degree: int = 1,
        connectors: list[str] | None = None,
        min_confidence: float = 0.0,
        max_fanout: int = DEFAULT_MAX_FANOUT,
        max_persons: int = DEFAULT_MAX_PERSONS,
    ) -> dict | None:
```

Then replace the body of the `for level in ...` loop's link-merging and frontier-building section with:

```python
        for level in range(1, degree + 1):
            if not frontier:
                break
            found = self._expand_level(frontier, set(persons), edges, max_fanout)
            suppressed.update(found.suppressed_hubs)

            # Filtering before the frontier is built is what makes the
            # threshold cut the path rather than just hide one edge: a person
            # only reachable through a link too weak to show is not reachable.
            reachable: set[str] = set()
            for key, via in found.links.items():
                if _link_confidence(via) < min_confidence:
                    continue
                reachable.update(key)
                link = links.get(key)
                if link is None:
                    links[key] = {
                        "source": key[0],
                        "target": key[1],
                        "degree": level,
                        "via": list(via),
                    }
                else:
                    _merge_via(link["via"], via)

            next_frontier: list[str] = []
            for vid in sorted(found.persons):
                if vid in persons or vid not in reachable:
                    continue
                if len(persons) >= max_persons:
                    truncated = True
                    break
                persons[vid] = _person_payload(found.persons[vid], level)
                next_frontier.append(vid)
            frontier = next_frontier
```

Finally add `min_confidence` to the returned payload so a client can echo the threshold it got:

```python
        return {
            "root_id": root_id,
            "degree": degree,
            "min_confidence": min_confidence,
            "persons": sorted(persons.values(), key=lambda p: (p["degree"], p["label"])),
            "links": sorted(kept_links, key=lambda link: (link["degree"], link["source"])),
            "truncated": truncated,
            "suppressed_hubs": sorted(
                suppressed.values(), key=lambda hub: -hub["person_count"]
            ),
            "connectors": {
                "direct": list(edges.direct),
                "shared": list(edges.shared),
                "bridge": list(edges.bridge),
            },
        }
```

- [ ] **Step 4: Expose it on the router**

In `routers/entities.py`, add the query parameter to `person_network` after `connectors`:

```python
    min_confidence: float = Query(
        0.0, ge=0.0, le=1.0, description="Drop links scoring below this confidence"
    ),
```

and pass it through to the service call:

```python
    network = service.person_network(
        root_id=entity_id,
        degree=degree,
        connectors=connectors.split(",") if connectors else None,
        min_confidence=min_confidence,
        max_fanout=max_fanout,
        max_persons=max_persons,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/ -v`
Expected: PASS (whole unit suite)

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/graph_explorer_api/services/person_network_service.py \
        apps/api/src/graph_explorer_api/routers/entities.py \
        apps/api/tests/unit/test_person_network_service.py
git commit -m "feat(api): filter the person network by link confidence"
```

---

## Task 9: Expand a person to documents only

**Files:**
- Modify: `apps/api/src/graph_explorer_api/services/person_network_service.py:177-215`
- Test: `apps/api/tests/unit/test_person_network_service.py`

**Interfaces:**
- Consumes: `FIELD_VALUE_TAG` (Task 7).
- Produces: `attributes()` returning only `document`-tagged connectors, never `field_value` ones.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_person_network_service.py`:

```python
@pytest.fixture
def person_with_everything():
    return make_service(
        {
            "a": person("Alice"),
            "doc:1": thing("document", "P1234567"),
            "phone:1": thing("phone", "+91-111"),
            "value:1": value_node("ahmed"),
        },
        [
            ("a", "doc:1", "HAS_DOCUMENT"),
            ("a", "phone:1", "HAS_PHONE"),
            ("a", "value:1", FIELD_VALUE, {"field_key": "father_name"}),
        ],
    )


def test_expanding_a_person_yields_only_documents(person_with_everything):
    result = person_with_everything.attributes("a")
    assert [a["tag"] for a in result["attributes"]] == ["document"]


def test_expanding_a_person_never_leaks_index_vertices(person_with_everything):
    """field_value vertices are an index, not something to draw."""
    result = person_with_everything.attributes("a")
    assert all(a["tag"] != "field_value" for a in result["attributes"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest apps/api/tests/unit/test_person_network_service.py -v -k "expanding_a_person"`
Expected: FAIL — the list contains `document`, `field_value` and `phone`.

- [ ] **Step 3: Narrow the expansion**

Add a constant next to `FIELD_VALUE_TAG`:

```python
# What a person expands into on the canvas. Phone/email/account/vehicle are
# still ingested and still form links — they are simply not what an
# investigator opens a person to look at.
EXPANDABLE_TAGS: frozenset[str] = frozenset({"document"})
```

In `attributes()`, replace the `connector_ids` assignment:

```python
        connector_ids = [
            vid
            for vid, vertex in vertices.items()
            if PERSON_TAG not in vertex.tags and _primary_tag(vertex) in EXPANDABLE_TAGS
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest apps/api/tests/unit/test_person_network_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/graph_explorer_api/services/person_network_service.py \
        apps/api/tests/unit/test_person_network_service.py
git commit -m "feat(api): expand a person into documents only"
```

---

## Task 10: Frontend types and client

**Files:**
- Modify: `apps/web/src/api/types.ts:123-172`
- Modify: `apps/web/src/api/client.ts:131-143`

**Interfaces:**
- Consumes: the API shape from Tasks 7-8.
- Produces: the `shared_field` variant of `PersonLinkVia`; `PersonLink.confidence`; `api.getPersonNetwork(id, degree, { minConfidence })`.

- [ ] **Step 1: Add the via variant and link confidence**

In `types.ts`, add this member to the `PersonLinkVia` union, after the `shared_attribute` member:

```ts
  /** Two people whose *separate* documents agree on a value — the same
   * father's name on two passports. `connector_label` is the matched value
   * itself. */
  | {
      kind: 'shared_field'
      connector_id: string
      connector_tag: 'field_value'
      connector_label: string
      field_key: string
      field_keys: string[]
      same_key: boolean
      edge_types: string[]
      confidence: number
    }
```

Add `confidence` to `PersonLink`:

```ts
export interface PersonLink {
  source: string
  target: string
  degree: number
  /** Human-readable summary of `via`, e.g. "shared phone". */
  label: string
  /** 0-1. Independent reasons compound, so this is not the best `via`'s
   * score but the noisy-OR across all of them. */
  confidence: number
  via: PersonLinkVia[]
}
```

Add `min_confidence` to `PersonNetwork`:

```ts
export interface PersonNetwork {
  root_id: string
  degree: number
  min_confidence: number
  persons: PersonNode[]
  links: PersonLink[]
  truncated: boolean
  suppressed_hubs: SuppressedHub[]
  connectors: { direct: string[]; shared: string[] }
}
```

- [ ] **Step 2: Pass the threshold through the client**

In `client.ts`, update `getPersonNetwork`:

```ts
  getPersonNetwork: (
    entityId: string,
    degree = 1,
    opts?: { connectors?: string[]; maxFanout?: number; maxPersons?: number; minConfidence?: number },
  ) =>
    request<PersonNetwork>(
      `/api/entities/${encodeURIComponent(entityId)}/person-network${qs({
        degree,
        connectors: opts?.connectors?.join(','),
        max_fanout: opts?.maxFanout,
        max_persons: opts?.maxPersons,
        min_confidence: opts?.minConfidence,
      })}`,
    ),
```

- [ ] **Step 3: Verify the frontend still type-checks**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/api/types.ts apps/web/src/api/client.ts
git commit -m "feat(web): type matching-field links and the confidence threshold"
```

---

## Task 11: Confidence-weighted edges and expansion that survives a degree change

**Files:**
- Modify: `apps/web/src/components/explorer/graphStyle.ts:39-45`
- Modify: `apps/web/src/hooks/usePersonNetworkState.ts:34-51,124-146`
- Modify: `apps/web/src/pages/InvestigationPage.tsx:152-176`

**Interfaces:**
- Consumes: `PersonLink.confidence` (Task 10).
- Produces: `edgeConfidence(edge: GraphEdge): number`; `loadNetwork(rootId, degree, opts?: { minConfidence?: number; preserveExpanded?: boolean })`.

- [ ] **Step 1: Add the edge-confidence accessor**

In `graphStyle.ts`, after `edgeWeight`, add:

```ts
/** How confident the projection is in this link, 0-1. Investigation's
 * person links carry it; anything else is treated as certain, because a
 * stored edge is an assertion rather than an inference. */
export function edgeConfidence(edge: GraphEdge): number {
  const confidence = Number(edge.properties?.confidence)
  return Number.isFinite(confidence) ? Math.min(1, Math.max(0, confidence)) : 1
}
```

- [ ] **Step 2: Carry confidence onto the canvas edges**

In `usePersonNetworkState.ts`, update the `canvasEdges` person-link mapping:

```ts
    const edges: GraphEdge[] = (network?.links ?? []).map((link) => ({
      src: link.source,
      dst: link.target,
      edge_type: link.label,
      rank: 0,
      // relationship_type is what the canvas prefers as an edge label,
      // via_count scales the link's width, and confidence fades it.
      properties: {
        relationship_type: link.label,
        via_count: link.via.length,
        confidence: link.confidence,
      },
    }))
```

- [ ] **Step 3: Preserve expansion across a degree change**

In `usePersonNetworkState.ts`, replace `loadNetwork`:

```ts
  const loadNetwork = useCallback(
    async (
      rootId: string,
      degree: number,
      opts?: { minConfidence?: number; preserveExpanded?: boolean },
    ) => {
      setLoadingNetwork(true)
      setError(null)
      try {
        const result = await api.getPersonNetwork(rootId, degree, {
          minConfidence: opts?.minConfidence,
        })
        setNetwork(result)
        // Raising the degree is the same question asked wider, so which
        // people the user had opened still applies. A new root is a new
        // question, and nothing carries over but the attribute cache.
        if (!opts?.preserveExpanded) setExpanded(new Set())
        return result
      } catch (err) {
        setNetwork(null)
        setError((err as Error).message)
        return null
      } finally {
        setLoadingNetwork(false)
      }
    },
    [],
  )
```

- [ ] **Step 4: Pass the flag from the degree handler**

In `InvestigationPage.tsx`, widen the local wrapper at line 152 and the degree handler at 174-176:

```tsx
  async function loadNetwork(
    personId: string,
    nextDegree: number,
    opts?: { preserveExpanded?: boolean },
  ) {
    setStatus(`Finding connections within ${nextDegree} degree${nextDegree === 1 ? '' : 's'}…`)
    const result = await graph.loadNetwork(personId, nextDegree, {
      minConfidence,
      preserveExpanded: opts?.preserveExpanded,
    })
```

(the rest of the function body is unchanged), and:

```tsx
    setDegree(next)
    if (rootId) await loadNetwork(rootId, next, { preserveExpanded: true })
```

`minConfidence` is the state added in Task 12; add it now as `const [minConfidence, setMinConfidence] = useState(0)` next to the existing `const [degree, setDegree] = useState(1)` so this task compiles on its own.

- [ ] **Step 5: Verify it type-checks**

Run: `cd apps/web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/explorer/graphStyle.ts \
        apps/web/src/hooks/usePersonNetworkState.ts \
        apps/web/src/pages/InvestigationPage.tsx
git commit -m "feat(web): weight links by confidence and keep expansion across degrees"
```

---

## Task 12: Confidence slider and link explanations in the right panel

**Files:**
- Modify: `apps/web/src/pages/InvestigationPage.tsx:300-315,388-520`

**Interfaces:**
- Consumes: `minConfidence` state (Task 11); `PersonLinkVia`'s `shared_field` variant (Task 10).
- Produces: no new exports — this is the view layer.

- [ ] **Step 1: Add the slider next to the degree selector**

In the controls row that holds the degree `<select>` (around line 305), add after it:

```tsx
          <label className="control">
            <span>Min confidence: {minConfidence.toFixed(2)}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              onPointerUp={() => {
                if (rootId) void loadNetwork(rootId, degree, { preserveExpanded: true })
              }}
              aria-label="Minimum link confidence"
            />
          </label>
```

Re-querying on `pointerup` rather than on every `change` keeps one request per drag instead of one per step.

- [ ] **Step 2: Render the matched-field explanation**

`viaText` (`InvestigationPage.tsx:33-41`) turns a `via` into a sentence. The new branch must sit **before** the final `return via.label`, because `shared_field` has no `label` field and TypeScript will reject the fallthrough. Replace the whole function with:

```tsx
function viaText(via: PersonLinkVia): string {
  // Only a shared_attribute or a shared_field is something the two people
  // have in common; the other kinds carry a ready sentence, and rendering
  // them as "company: X" would claim they share X when they don't.
  if (via.kind === 'shared_attribute') {
    return `${via.connector_tag.replace(/_/g, ' ')}: ${via.connector_label}`
  }
  if (via.kind === 'shared_field') {
    const keys = via.same_key
      ? via.field_key.replace(/_/g, ' ')
      : via.field_keys.map((k) => k.replace(/_/g, ' ')).join(' ↔ ')
    return `matching ${keys}: “${via.connector_label}”`
  }
  return via.label
}
```

- [ ] **Step 3: Show a selected link's reasons in the panel**

The detail panel currently branches on a selected person and a selected attribute. Add a third branch, rendered when a link is selected, alongside those:

```tsx
            {selectedLink && (
              <div className="panel stack">
                <h2>Connection</h2>
                <p className="muted">
                  {graph.personsById.get(selectedLink.source)?.label ?? selectedLink.source}
                  {' ↔ '}
                  {graph.personsById.get(selectedLink.target)?.label ?? selectedLink.target}
                </p>
                <p>
                  Confidence {selectedLink.confidence.toFixed(2)} · degree {selectedLink.degree}
                </p>
                <ul>
                  {selectedLink.via.map((via, i) => (
                    <li key={i}>{viaText(via)}</li>
                  ))}
                </ul>
              </div>
            )}
```

Track the selection with state next to `selectedVid`:

```tsx
  const [selectedLinkKey, setSelectedLinkKey] = useState<string | null>(null)
  const selectedLink = useMemo(
    () =>
      (graph.network?.links ?? []).find(
        (l) => `${l.source}->${l.target}` === selectedLinkKey,
      ) ?? null,
    [graph.network, selectedLinkKey],
  )
```

Replace `describeVia` with whatever the existing helper at line ~36-40 is named.

- [ ] **Step 4: Verify it type-checks and builds**

Run: `cd apps/web && npx tsc --noEmit && npm run build`
Expected: no errors; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/InvestigationPage.tsx
git commit -m "feat(web): add a confidence filter and link explanations to the detail panel"
```

---

## Task 13: Backfill the index over existing data

**Files:**
- Create: `scripts/reindex_field_values.py`

**Interfaces:**
- Consumes: `field_values`/`value_vid` (Task 3), `GraphWriter.index_field_values` (Task 5).
- Produces: a CLI entry point; no importable API.

- [ ] **Step 1: Write the script**

Create `scripts/reindex_field_values.py`:

```python
"""Rebuild the field-value index over an already-ingested space.

Existing spaces predate the index and their documents predate the generic
`document` tag, so the graph has people and documents but no `field_value`
vertices at all. This walks what is there and emits the index under the
current denylist and normalisation rules.

Re-runnable by construction: INSERT VERTEX overwrites by vid and the value
vid is a pure function of the value, so a second run after retuning the
denylist converges rather than duplicating.

    .venv/bin/python scripts/reindex_field_values.py --space intel_kg_v2
    .venv/bin/python scripts/reindex_field_values.py --space intel_kg_v2 --dry-run
"""

from __future__ import annotations

import argparse
import os

from graph_core.client import GraphClient
from graph_core.config import GraphConfig
from graph_explorer_api.services.entity_props import merged_properties
from intelligence_schema.field_index import field_values
from intelligence_schema.graph_writer import GraphWriter

PERSON_TAG = "person"
DOCUMENT_TAG = "document"


def _person_ids(client: GraphClient) -> list[str]:
    result = client.execute_raw(f"LOOKUP ON {PERSON_TAG} YIELD id(vertex) AS vid;")
    return [str(row["vid"]) for row in (result.rows or [])]


def _documents_of(client: GraphClient, person_id: str) -> list[str]:
    result = client.execute_raw(
        f'GO FROM "{person_id}" OVER HAS_DOCUMENT YIELD dst(edge) AS vid;'
    )
    return [str(row["vid"]) for row in (result.rows or [])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default=os.environ.get("NEBULA_SPACE", "intel_kg_v2"))
    parser.add_argument(
        "--dry-run", action="store_true", help="Count what would be indexed, write nothing"
    )
    args = parser.parse_args()

    client = GraphClient(GraphConfig.from_env(), space=args.space)
    writer = GraphWriter(client)
    people = _person_ids(client)
    values_indexed = 0
    documents_seen = 0

    try:
        for person_id in people:
            vertex = next(iter(client.vertices.get_many_raw([person_id])), None)
            if vertex is None:
                continue
            own = merged_properties(vertex)
            if args.dry_run:
                values_indexed += len(field_values(own))
            else:
                values_indexed += writer.index_field_values(person_id, own)

            for document_id in _documents_of(client, person_id):
                document = next(iter(client.vertices.get_many_raw([document_id])), None)
                if document is None:
                    continue
                documents_seen += 1
                props = merged_properties(document)
                if args.dry_run:
                    values_indexed += len(field_values(props))
                else:
                    values_indexed += writer.index_field_values(
                        person_id,
                        props,
                        document_id=document_id,
                        document_type=str(props.get("document_type") or "document"),
                    )
    finally:
        client.close()

    verb = "would index" if args.dry_run else "indexed"
    print(
        f"{len(people)} people, {documents_seen} documents, {verb} {values_indexed} values "
        f"in space {args.space}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script's imports and CLI resolve**

Run: `.venv/bin/python scripts/reindex_field_values.py --help`
Expected: the usage message prints, listing `--space` and `--dry-run`.

- [ ] **Step 3: Commit**

```bash
git add scripts/reindex_field_values.py
git commit -m "feat: add a re-runnable field-value reindex job"
```

- [ ] **Step 4: Run it against real data (ASK FIRST)**

`CLAUDE.md` requires asking before starting the stack — shared box, NebulaGraph is memory-hungry. Ask the user, then check `free -h`, then:

```bash
./dev                 # wait for "Storage host registered" in the console log
.venv/bin/python scripts/reindex_field_values.py --space intel_kg_v2 --dry-run
```

Report the counts before running for real without `--dry-run`. Tear down with `./dev down` (never `-v`, which wipes the ingested graph).

---

## Task 14: Verify the whole flow end to end (ASK FIRST)

**Files:** none — verification only.

**Interfaces:**
- Consumes: every preceding task.
- Produces: nothing.

- [ ] **Step 1: Run the whole backend suite**

Run: `.venv/bin/pytest apps/api/tests/ -v`
Expected: PASS, no regressions.

- [ ] **Step 2: Build the frontend**

Run: `cd apps/web && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 3: Check the running app (ask before starting the stack)**

Ask the user first. Then `./dev`, and confirm on the Investigation page:

- Searching a person renders person nodes only, at degree 1 by default.
- Clicking a person reveals document sub-nodes — no phone, email, bank account, vehicle, and no `field_value` nodes.
- Clicking a document shows its full field list **in the right-hand panel**, not on the canvas.
- Switching to degree 2 widens the graph and **keeps** the people already expanded.
- Dragging the confidence slider up removes weak links, and removes people only reachable through them.
- Selecting a link shows which field matched, the matched value, and the confidence.

Report what you actually saw. Tear down with `./dev down`.

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §1 Document model / Emirates ID | 1, 2, 4 |
| §2 Value index, denylist, normalisation | 3, 4, 5 |
| §3 Confidence (weights, rarity, cross-key, noisy-OR) | 6, 7 |
| §4 Degree traversal, `HAS_DOCUMENT` in `SHARED_EDGES`, `min_confidence` cutting the path | 7, 8 |
| §5 API (`min_confidence`, documents-only expansion, link reasons) | 8, 9 |
| §6 Frontend (document-only sub-nodes, degree merge, confidence UI, right panel) | 9, 10, 11, 12 |
| §7 Testing | tests inside 1, 3, 6, 7, 8, 9; suite runs in 14 |
| §8 Backfill | 13 |
| §9 Out of scope (no fuzzy matching) | Global Constraints |
| §10 Risks (graph size reporting) | 13 (the job prints counts) |

**Known follow-ups, deliberately not in this plan:** `reasoning_core/enrichment.py` also references `HAS_PASSPORT` (found by `grep -rln HAS_PASSPORT`). Task 1 changes the ontology it reads from, so whoever runs Task 1 should grep for `HAS_PASSPORT` once more and update that call site in the same commit if it still refers to the old edge type.
