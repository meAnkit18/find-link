# Connection Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an investigator search two people by name on the Investigation page and get back the strongest chain connecting them (with confidence and reasons per hop), or a clear "not connected" answer — replacing the existing raw, JSON-dumping "Path from here"/"Path to here" flow.

**Architecture:** A new `PersonNetworkService.find_connection` method reuses the existing `person_network` BFS projection (same confidence/reason machinery already powering the Investigation page) one degree past its normal cap, then runs Dijkstra over the resulting link graph to pick the highest-confidence chain. A new `GET /api/entities/{entity_id}/connection/{target_id}` endpoint exposes it. The Investigation page gains a mode toggle; "Verify connection" mode shows two person-search boxes and a new `ConnectionChainView` component that renders the chain by reusing the existing `describeLink`/`ReasonCard` reason-rendering already used elsewhere on the page.

**Tech Stack:** Python/FastAPI backend (`apps/api`), fake-graph-client unit tests (pytest); React/TypeScript frontend (`apps/web`), Vite, vitest.

## Global Constraints

- Backend tests run with the fake `GraphClient` — no live NebulaGraph needed: `cd apps/api && ../../.venv/bin/pytest tests/unit -v`.
- Frontend typecheck is `npm run build` (`tsc -b && vite build`) inside `apps/web` — `tsc --noEmit` alone is known to pass code that doesn't actually compile; always use `npm run build` to verify.
- Keep changes as small as possible; don't touch behavior this plan doesn't call for.
- The search depth for connection-finding is a fixed 4 hops, not user-adjustable, and not exposed as a query parameter.
- Only the single strongest path is returned — never multiple candidate paths.
- The existing `/api/entities/shortest-path` endpoint and `api.shortestPath` client method are untouched; they keep backing the Entities/Risk page, Agent Tools page, and API Console page.

---

### Task 1: `PersonNetworkService.find_connection`

**Files:**
- Modify: `apps/api/src/graph_explorer_api/services/person_network_service.py`
- Test: `apps/api/tests/unit/test_person_network_service.py`

**Interfaces:**
- Consumes: the existing `person_network(root_id, degree, connectors=None, min_confidence=0.0, max_fanout=DEFAULT_MAX_FANOUT, max_persons=DEFAULT_MAX_PERSONS)` method on the same class, and `PERSON_TAG`, `MAX_DEGREE` module constants already defined in this file.
- Produces: `PersonNetworkService.find_connection(source_id: str, target_id: str, max_degree: int = MAX_CONNECTION_DEGREE) -> dict | None`, returning:
  - `None` when `source_id` isn't a person (router turns this into 404).
  - `{"error": "same_person"}` when `source_id == target_id`.
  - `{"error": "target_not_found"}` when `target_id` isn't a person vertex.
  - `{"connected": False, "source_id", "target_id", "max_degree_searched"}` when unreachable within `max_degree`.
  - `{"connected": True, "source_id", "target_id", "path": {"persons": [...], "links": [...], "confidence": float}}` when connected — `persons`/`links` are the same dict shapes `person_network` already returns.
  - Also adds `max_degree_cap: int = MAX_DEGREE` as a new optional keyword to `person_network` (default preserves all existing behavior/tests unchanged) and a new module constant `MAX_CONNECTION_DEGREE = 4`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_person_network_service.py` (after the existing `test_matching_field_names_the_source_documents` test at the end of the file):

```python
# ------------------------------------------------------- connection finder


def test_find_connection_returns_the_direct_link(shared_phone):
    result = shared_phone.find_connection("a", "b")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b"]
    assert len(result["path"]["links"]) == 1
    assert result["path"]["confidence"] == pytest.approx(0.8)


def test_find_connection_walks_a_multi_hop_chain(chain):
    result = chain.find_connection("a", "d")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b", "c", "d"]
    assert len(result["path"]["links"]) == 3


def test_find_connection_reports_not_connected():
    service = make_service(
        {"a": person("Alice"), "b": person("Bob")},
        [],
    )
    result = service.find_connection("a", "b")
    assert result == {
        "connected": False,
        "source_id": "a",
        "target_id": "b",
        "max_degree_searched": 4,
    }


def test_find_connection_looks_one_degree_past_the_exploration_cap():
    """A 4-hop chain is out of reach for person_network's own degree=3 cap,
    but find_connection's default of 4 should still find it."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "d": person("Dan"),
            "e": person("Eve"),
            "phone:1": thing("phone", "+91-111"),
            "phone:2": thing("phone", "+91-222"),
            "phone:3": thing("phone", "+91-333"),
            "phone:4": thing("phone", "+91-444"),
        },
        [
            ("a", "phone:1", "HAS_PHONE"),
            ("b", "phone:1", "HAS_PHONE"),
            ("b", "phone:2", "HAS_PHONE"),
            ("c", "phone:2", "HAS_PHONE"),
            ("c", "phone:3", "HAS_PHONE"),
            ("d", "phone:3", "HAS_PHONE"),
            ("d", "phone:4", "HAS_PHONE"),
            ("e", "phone:4", "HAS_PHONE"),
        ],
    )
    assert "e" not in {p["id"] for p in service.person_network("a", degree=3)["persons"]}
    result = service.find_connection("a", "e")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "b", "c", "d", "e"]


def test_find_connection_prefers_the_stronger_of_two_equal_length_routes():
    """a-b-target is a weak city match then a direct edge; a-c-target is a
    strong passport match then the same kind of direct edge. Both routes are
    2 hops; the stronger (passport) route should win."""
    service = make_service(
        {
            "a": person("Alice"),
            "b": person("Bob"),
            "c": person("Carol"),
            "target": person("Target"),
            "value:city": value_node("dubai"),
            "value:pp": value_node("p1234567"),
        },
        [
            ("a", "value:city", FIELD_VALUE, {"field_key": "city"}),
            ("b", "value:city", FIELD_VALUE, {"field_key": "city"}),
            ("b", "target", "RELATED_TO"),
            ("a", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
            ("c", "value:pp", FIELD_VALUE, {"field_key": "passport_number"}),
            ("c", "target", "RELATED_TO"),
        ],
    )
    result = service.find_connection("a", "target")
    assert result["connected"] is True
    assert [p["id"] for p in result["path"]["persons"]] == ["a", "c", "target"]


def test_find_connection_rejects_the_same_person(shared_phone):
    assert shared_phone.find_connection("a", "a") == {"error": "same_person"}


def test_find_connection_rejects_an_unknown_target(shared_phone):
    assert shared_phone.find_connection("a", "nobody") == {"error": "target_not_found"}


def test_find_connection_rejects_a_non_person_target(shared_phone):
    assert shared_phone.find_connection("a", "phone:1") == {"error": "target_not_found"}


def test_find_connection_returns_none_for_an_unknown_source(shared_phone):
    assert shared_phone.find_connection("nobody", "a") is None


def test_person_network_max_degree_cap_extends_past_max_degree(chain):
    """Internal callers (find_connection) can look further than the public
    API's degree ceiling; the router never passes this, so MAX_DEGREE=3
    keeps capping every request that doesn't set it explicitly."""
    network = chain.person_network("a", degree=4, max_degree_cap=4)
    assert network["degree"] == 4
    assert chain.person_network("a", degree=9)["degree"] == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit/test_person_network_service.py -v -k "find_connection or max_degree_cap"`
Expected: FAIL with `AttributeError: 'PersonNetworkService' object has no attribute 'find_connection'` (and a `TypeError` on the unexpected `max_degree_cap` keyword).

- [ ] **Step 3: Add `heapq`/`math` imports and the `MAX_CONNECTION_DEGREE` constant**

In `apps/api/src/graph_explorer_api/services/person_network_service.py`, change the top of the file from:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Callable, NamedTuple
```

to:

```python
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Callable, NamedTuple
```

Then change:

```python
DEFAULT_MAX_FANOUT = 25
DEFAULT_MAX_PERSONS = 300
MAX_DEGREE = 3
```

to:

```python
DEFAULT_MAX_FANOUT = 25
DEFAULT_MAX_PERSONS = 300
MAX_DEGREE = 3

# find_connection searches one degree past the public exploration ceiling —
# a deliberate "are these two connected" question can afford to look
# slightly further than casual browsing. Not exposed as an API parameter.
MAX_CONNECTION_DEGREE = 4
```

- [ ] **Step 4: Add `max_degree_cap` to `person_network`**

Change:

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
        """Persons within `degree` connections of `root_id`, and why.

        Returns None when the root doesn't exist or isn't a person — the
        router turns that into a 404.
        """
        degree = max(1, min(int(degree), MAX_DEGREE))
```

to:

```python
    def person_network(
        self,
        root_id: str,
        degree: int = 1,
        connectors: list[str] | None = None,
        min_confidence: float = 0.0,
        max_fanout: int = DEFAULT_MAX_FANOUT,
        max_persons: int = DEFAULT_MAX_PERSONS,
        max_degree_cap: int = MAX_DEGREE,
    ) -> dict | None:
        """Persons within `degree` connections of `root_id`, and why.

        Returns None when the root doesn't exist or isn't a person — the
        router turns that into a 404.

        `max_degree_cap` overrides the degree ceiling for internal callers
        that need to look further than the public API allows (see
        `find_connection`). The router never passes it, so every request
        that comes in through `/person-network` still clamps to MAX_DEGREE.
        """
        degree = max(1, min(int(degree), max_degree_cap))
```

- [ ] **Step 5: Add `find_connection`**

Insert the following method directly after `person_network` (before the `attributes` method):

```python
    def find_connection(
        self, source_id: str, target_id: str, max_degree: int = MAX_CONNECTION_DEGREE
    ) -> dict | None:
        """The strongest chain connecting two people, if any, within
        `max_degree` hops of `source_id`.

        "Strongest" maximizes the product of each hop's confidence (ties
        broken by fewest hops) — see `_strongest_path`.

        Returns None when `source_id` isn't a person (the router 404s).
        Returns `{"error": ...}` for a same-person request or an unknown/
        non-person target — the router turns those into 400s, distinct from
        a legitimate "not connected" answer.
        """
        if source_id == target_id:
            return {"error": "same_person"}

        target_vertex = self._fetch_vertices([target_id]).get(target_id)
        if target_vertex is None or PERSON_TAG not in target_vertex.tags:
            return {"error": "target_not_found"}

        network = self.person_network(
            source_id, degree=max_degree, max_degree_cap=max_degree
        )
        if network is None:
            return None

        persons_by_id = {p["id"]: p for p in network["persons"]}
        if target_id not in persons_by_id:
            return {
                "connected": False,
                "source_id": source_id,
                "target_id": target_id,
                "max_degree_searched": max_degree,
            }

        path_ids, path_links, confidence = _strongest_path(
            source_id, target_id, network["links"]
        )
        return {
            "connected": True,
            "source_id": source_id,
            "target_id": target_id,
            "path": {
                "persons": [persons_by_id[vid] for vid in path_ids],
                "links": path_links,
                "confidence": confidence,
            },
        }
```

- [ ] **Step 6: Add the `_strongest_path` helper**

Insert this module-level function in the "helpers" section at the bottom of the file, directly after `_finalize_link`:

```python
def _strongest_path(
    source_id: str, target_id: str, links: list[dict]
) -> tuple[list[str], list[dict], float]:
    """Dijkstra over `links` (already-finalized person_network links, each
    carrying a `confidence` in (0, 1]), weighted to maximize the product of
    hop confidences — equivalently minimize the sum of -log(confidence).
    Ties (equal weight) prefer fewer hops, via the second element of the
    priority tuple.

    `links` is undirected: a link's `source`/`target` order is whichever
    the projection discovered first, not a direction. `target_id` must be
    reachable from `source_id` through `links` — the caller only calls this
    after confirming target_id is among the persons the same BFS produced.
    """
    adjacency: dict[str, list[dict]] = defaultdict(list)
    for link in links:
        adjacency[link["source"]].append(link)
        adjacency[link["target"]].append(link)

    best: dict[str, tuple[float, int]] = {source_id: (0.0, 0)}
    came_from: dict[str, tuple[str, dict]] = {}
    visited: set[str] = set()
    frontier: list[tuple[float, int, str]] = [(0.0, 0, source_id)]

    while frontier:
        weight, hops, current = heapq.heappop(frontier)
        if current in visited:
            continue
        visited.add(current)
        if current == target_id:
            break

        for link in adjacency[current]:
            neighbor = link["target"] if link["source"] == current else link["source"]
            if neighbor in visited:
                continue
            confidence = max(float(link["confidence"]), 1e-9)
            candidate = (weight - math.log(confidence), hops + 1)
            if neighbor not in best or candidate < best[neighbor]:
                best[neighbor] = candidate
                came_from[neighbor] = (current, link)
                heapq.heappush(frontier, (candidate[0], candidate[1], neighbor))

    path_ids = [target_id]
    path_links: list[dict] = []
    node = target_id
    while node != source_id:
        prev, link = came_from[node]
        path_links.append(link)
        path_ids.append(prev)
        node = prev
    path_ids.reverse()
    path_links.reverse()

    total_weight, _ = best[target_id]
    return path_ids, path_links, math.exp(-total_weight)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit/test_person_network_service.py -v`
Expected: PASS — every test in the file, including the new ones and every pre-existing one (confirming `max_degree_cap`'s default kept `person_network`'s old behavior intact).

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/graph_explorer_api/services/person_network_service.py apps/api/tests/unit/test_person_network_service.py
git commit -m "feat(api): add find_connection to project the strongest chain between two people"
```

---

### Task 2: `GET /api/entities/{entity_id}/connection/{target_id}`

**Files:**
- Modify: `apps/api/src/graph_explorer_api/routers/entities.py`
- Test: `apps/api/tests/unit/test_person_network_router.py`

**Interfaces:**
- Consumes: `PersonNetworkService.find_connection` from Task 1, `get_person_network_service` dependency already imported in this router.
- Produces: `GET /api/entities/{entity_id}/connection/{target_id}` → 200 with the `find_connection` payload, 404 when `entity_id` isn't a person, 400 when `target_id` is the same as `entity_id` or isn't a person.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/unit/test_person_network_router.py`, change the `service` fixture from:

```python
@pytest.fixture
def service():
    clients = FakeGraphClientCache()
    store = clients.for_space(SPACE).store
    store.vertices.update(
        {
            "a": {"person": {"label": "Alice", "entity_type": "Person"}},
            "b": {"person": {"label": "Bob", "entity_type": "Person"}},
            "doc:1": {"document": {"label": "P1234567", "entity_type": "Document"}},
        }
    )
    store.edges.extend(
        [
            ("a", "doc:1", "HAS_DOCUMENT", 0, {}),
            ("b", "doc:1", "HAS_DOCUMENT", 0, {}),
        ]
    )
    store.edge_types["HAS_DOCUMENT"] = object()
    return PersonNetworkService(clients, SPACE)
```

to (adding an isolated `lonely` person, unreachable from `a`/`b`, for the not-connected test):

```python
@pytest.fixture
def service():
    clients = FakeGraphClientCache()
    store = clients.for_space(SPACE).store
    store.vertices.update(
        {
            "a": {"person": {"label": "Alice", "entity_type": "Person"}},
            "b": {"person": {"label": "Bob", "entity_type": "Person"}},
            "doc:1": {"document": {"label": "P1234567", "entity_type": "Document"}},
            "lonely": {"person": {"label": "Lonely", "entity_type": "Person"}},
        }
    )
    store.edges.extend(
        [
            ("a", "doc:1", "HAS_DOCUMENT", 0, {}),
            ("b", "doc:1", "HAS_DOCUMENT", 0, {}),
        ]
    )
    store.edge_types["HAS_DOCUMENT"] = object()
    return PersonNetworkService(clients, SPACE)
```

Then append these tests to the same file, after `test_attributes_endpoint_returns_shared_details`:

```python
def test_find_connection_returns_the_path(api):
    response = api.get("/api/entities/a/connection/b")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert [p["id"] for p in body["path"]["persons"]] == ["a", "b"]


def test_find_connection_reports_not_connected(api):
    response = api.get("/api/entities/a/connection/lonely")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "source_id": "a",
        "target_id": "lonely",
        "max_degree_searched": 4,
    }


def test_find_connection_404s_on_an_unknown_source(api):
    assert api.get("/api/entities/nobody/connection/a").status_code == 404


def test_find_connection_400s_on_the_same_person(api):
    assert api.get("/api/entities/a/connection/a").status_code == 400


def test_find_connection_400s_on_an_unknown_target(api):
    assert api.get("/api/entities/a/connection/nobody").status_code == 400


def test_find_connection_400s_on_a_non_person_target(api):
    assert api.get("/api/entities/a/connection/doc:1").status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit/test_person_network_router.py -v -k find_connection`
Expected: FAIL with 404s (route doesn't exist yet — FastAPI returns 404 for an undeclared path).

- [ ] **Step 3: Add the endpoint**

In `apps/api/src/graph_explorer_api/routers/entities.py`, insert the following directly after the `person_network` endpoint function and before `entity_attributes`:

```python
@router.get("/{entity_id}/connection/{target_id}")
def find_connection(
    entity_id: str,
    target_id: str,
    service: PersonNetworkService = Depends(get_person_network_service),
):
    result = service.find_connection(entity_id, target_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Person not found")
    if result.get("error") == "same_person":
        raise HTTPException(
            status_code=400, detail="Source and target must be different people"
        )
    if result.get("error") == "target_not_found":
        raise HTTPException(status_code=400, detail="Target person not found")
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit/test_person_network_router.py -v`
Expected: PASS — every test in the file.

- [ ] **Step 5: Run the full backend unit suite**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit -v`
Expected: PASS — nothing else in the backend depends on the changed files.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/graph_explorer_api/routers/entities.py apps/api/tests/unit/test_person_network_router.py
git commit -m "feat(api): expose find_connection as GET /entities/{id}/connection/{target_id}"
```

---

### Task 3: Frontend types and API client method

**Files:**
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/client.ts`

**Interfaces:**
- Consumes: the `GET /api/entities/{entity_id}/connection/{target_id}` endpoint from Task 2; the existing `PersonNode`/`PersonLink` types already declared in `types.ts`.
- Produces: `ConnectionResult` type, `api.findConnection(sourceId: string, targetId: string): Promise<ConnectionResult>`.

- [ ] **Step 1: Add the `ConnectionResult` type**

In `apps/web/src/api/types.ts`, directly after the closing brace of the `PersonNetwork` interface (before `export interface EntityAttribute`), add:

```ts
/** The result of asking whether two people are connected, and if so, how.
 * `path` reuses PersonNode/PersonLink, so the same reason-rendering the
 * Connections tab already does works here unchanged. */
export type ConnectionResult =
  | { connected: false; source_id: string; target_id: string; max_degree_searched: number }
  | {
      connected: true
      source_id: string
      target_id: string
      path: { persons: PersonNode[]; links: PersonLink[]; confidence: number }
    }
```

- [ ] **Step 2: Add the client method**

In `apps/web/src/api/client.ts`, add `ConnectionResult` to the type-only import block (it is alphabetized — insert between `CaseSummary` and `DeleteEvidenceResponse`):

```ts
import type {
  CancelEvidenceResponse,
  CaseCreated,
  CaseSummary,
  ConnectionResult,
  DeleteEvidenceResponse,
  Direction,
  ...
```

Then, directly after the `getPersonNetwork` method inside the `-- Entities --` section, add:

```ts
  /** The strongest chain connecting two people within 4 degrees, or a
   * "not connected" result. */
  findConnection: (sourceId: string, targetId: string) =>
    request<ConnectionResult>(
      `/api/entities/${encodeURIComponent(sourceId)}/connection/${encodeURIComponent(targetId)}`,
    ),
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npm run build`
Expected: succeeds with no TypeScript errors (this task only adds a type and a method; nothing calls `findConnection` yet, so no other file changes).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/api/types.ts apps/web/src/api/client.ts
git commit -m "feat(web): add ConnectionResult type and api.findConnection"
```

---

### Task 4: `PersonSearchField` component

**Files:**
- Create: `apps/web/src/components/explorer/connection/PersonSearchField.tsx`

**Interfaces:**
- Consumes: `api.searchEntities(query, entityType)` (existing), `PERSON_TAG` from `apps/web/src/hooks/usePersonNetworkState.ts` (existing), `EntitySearchHit` type (existing).
- Produces: `PersonSearchField` component with props `{ label: string; placeholder: string; selected: EntitySearchHit | null; onSelect: (hit: EntitySearchHit | null) => void }`. Used twice by Task 7 (Person A / Person B).

This is a UI component with no pure logic to unit test in isolation (it wraps `api.searchEntities`, already covered by the API layer); it's verified by the manual browser walkthrough in Task 8. There is no separate test step for this task — write it, then typecheck.

- [ ] **Step 1: Create the component**

```tsx
import { useState } from 'react'
import { Search } from 'lucide-react'
import { api } from '../../../api/client'
import type { EntitySearchHit } from '../../../api/types'
import { PERSON_TAG } from '../../../hooks/usePersonNetworkState'

interface Props {
  label: string
  placeholder: string
  selected: EntitySearchHit | null
  onSelect: (hit: EntitySearchHit | null) => void
}

/** A type-and-pick person search box, self-contained so the connection
 * finder can show two of them side by side without sharing state — one and
 * the same pattern as the single-person search on the Investigation page,
 * just parameterized for a slot instead of the page's own state. */
export default function PersonSearchField({ label, placeholder, selected, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EntitySearchHit[]>([])
  const [error, setError] = useState<string | null>(null)

  async function search() {
    if (!query.trim()) return
    setError(null)
    try {
      const hits = await api.searchEntities(query.trim(), PERSON_TAG)
      setResults(hits)
      if (hits.length === 0) setError('No people matched.')
    } catch (err) {
      setResults([])
      setError((err as Error).message)
    }
  }

  if (selected) {
    return (
      <div className="connection-picker">
        <span className="connection-picker__label">{label}</span>
        <div className="connection-picker__chosen">
          <strong>{selected.label || selected.entity_id}</strong>
          <button className="btn btn-sm" onClick={() => onSelect(null)}>
            Change
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="connection-picker" style={{ position: 'relative' }}>
      <span className="connection-picker__label">{label}</span>
      <div className="row" style={{ gap: 'var(--space-1)' }}>
        <div className="search-input-wrap">
          <Search className="search-input-wrap__icon" size={14} />
          <input
            className="input input--search"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <button className="btn btn-sm" onClick={search}>
          Search
        </button>
      </div>
      {error && (
        <div className="muted" style={{ marginTop: 'var(--space-1)' }}>
          {error}
        </div>
      )}
      {results.length > 0 && (
        <div className="card search-dropdown">
          {results.map((hit) => (
            <button
              key={hit.entity_id}
              className="list-item"
              onClick={() => {
                onSelect(hit)
                setResults([])
                setQuery('')
              }}
            >
              <strong>{hit.label || hit.entity_id}</strong>
              <div className="mono muted">{hit.entity_id}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && npm run build`
Expected: succeeds (the component isn't imported anywhere yet, so this only confirms the file itself compiles).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/explorer/connection/PersonSearchField.tsx
git commit -m "feat(web): add PersonSearchField for the connection finder"
```

---

### Task 5: `ConnectionChainView` component and styles

**Files:**
- Create: `apps/web/src/components/explorer/connection/ConnectionChainView.tsx`
- Modify: `apps/web/src/styles/graph-components.css`

**Interfaces:**
- Consumes: `ConnectionResult` type (Task 3), `describeLink` and `AttributeIndex` from `apps/web/src/components/explorer/detail/detailModel.ts` (existing), `ReasonCard` from `apps/web/src/components/explorer/detail/ReasonCard.tsx` (existing), `ConfidenceMeter`/`Callout` from `apps/web/src/components/explorer/detail/parts.tsx` (existing).
- Produces: `ConnectionChainView` component with props `{ sourceLabel: string; targetLabel: string; result: ConnectionResult; onExplore: (personId: string) => void }`. Used by Task 7.

- [ ] **Step 1: Add the chain CSS**

In `apps/web/src/styles/graph-components.css`, add the following block at the end of the file:

```css
/* ── Two-person connection chain (Verify connection mode) ── */

.connection-chain {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
  padding: var(--space-4);
  overflow-y: auto;
}

.connection-chain__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.connection-chain__hop {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.connection-chain__person {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

.connection-chain__reasons {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-left: var(--space-4);
  padding-left: var(--space-3);
  border-left: 2px solid var(--color-border);
}

/* ── The Person A / Person B pickers in the topbar ── */

.connection-picker {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.connection-picker__label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.connection-picker__chosen {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
```

- [ ] **Step 2: Create the component**

```tsx
import type { ConnectionResult, PersonNode } from '../../../api/types'
import { describeLink } from '../detail/detailModel'
import ReasonCard from '../detail/ReasonCard'
import { Callout, ConfidenceMeter } from '../detail/parts'

interface Props {
  sourceLabel: string
  targetLabel: string
  result: ConnectionResult
  onExplore: (personId: string) => void
}

// The chain view has no canvas/detail-panel selection framework behind it,
// so a reason's connector/document chips render as inert labels here —
// the same fallback ReasonCard already uses for a node the screen doesn't
// know about (see its `labelFor` contract).
const noLabel = () => null
const noOpen = () => {}

/** The answer to "are these two people connected, and why" — a plain,
 * standalone chain, independent of the canvas. Reuses `describeLink` and
 * `ReasonCard` unchanged, so each hop reads exactly like an entry in the
 * Connections tab. */
export default function ConnectionChainView({ sourceLabel, targetLabel, result, onExplore }: Props) {
  if (!result.connected) {
    return (
      <div className="connection-chain">
        <Callout>
          No connection found between <strong>{sourceLabel}</strong> and{' '}
          <strong>{targetLabel}</strong> within {result.max_degree_searched} degrees of
          separation.
        </Callout>
      </div>
    )
  }

  const { persons, links, confidence } = result.path
  const personsById = new Map(persons.map((p) => [p.id, p]))

  return (
    <div className="connection-chain">
      <div className="connection-chain__summary">
        <h3>
          {sourceLabel} → {targetLabel}
        </h3>
        <ConfidenceMeter value={confidence} label="Overall connection" />
      </div>

      {persons.map((person, i) => (
        <div className="connection-chain__hop" key={person.id}>
          <PersonRow person={person} isEndpoint={i === 0 || i === persons.length - 1} onExplore={onExplore} />
          {links[i] && (
            <div className="connection-chain__reasons">
              {describeLink(links[i], new Map(), personsById).map((descriptor, j) => (
                <ReasonCard key={j} descriptor={descriptor} labelFor={noLabel} onOpen={noOpen} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function PersonRow({
  person,
  isEndpoint,
  onExplore,
}: {
  person: PersonNode
  isEndpoint: boolean
  onExplore: (personId: string) => void
}) {
  return (
    <div className="connection-chain__person">
      <div>
        <strong>{person.label}</strong>
        {!isEndpoint && <span className="badge" style={{ marginLeft: 8 }}>via</span>}
      </div>
      <button className="btn btn-sm" onClick={() => onExplore(person.id)}>
        Explore this person
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npm run build`
Expected: succeeds (not imported anywhere yet).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/explorer/connection/ConnectionChainView.tsx apps/web/src/styles/graph-components.css
git commit -m "feat(web): add ConnectionChainView for the connection finder result"
```

---

### Task 6: Remove the old "Path from here" / "Path to here" flow

**Files:**
- Modify: `apps/web/src/pages/InvestigationPage.tsx`
- Modify: `apps/web/src/components/explorer/detail/PersonDetail.tsx`
- Modify: `apps/web/src/components/explorer/detail/DetailPanel.tsx`
- Modify: `apps/web/src/components/explorer/detail/LinkDetail.tsx`
- Modify: `apps/web/src/components/explorer/detail/detailModel.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DetailActions` (in `detailModel.ts`) no longer has `setPathSource`/`runPath`/`tracePath`; `DetailPanel`/`PersonDetail` no longer take a `pathSource` prop. Task 7 relies on `DetailActions` and `DetailPanel`'s prop list being exactly what remains after this task.

This is a deletion-only task with no new behavior to unit test; it's verified by the typecheck (a dangling reference to a removed prop/method is a compile error) and the full build.

- [ ] **Step 1: Strip `pathSource`/`runPath`/`tracePath` from `detailModel.ts`**

In `apps/web/src/components/explorer/detail/detailModel.ts`, change:

```ts
export interface DetailActions {
  select: (selection: Selection | null) => void
  /** Select a vid without the caller having to know whether it's a person or
   * an attribute. */
  openVid: (vid: string) => void
  /** A vid's display label, or null when nothing on screen knows it. */
  labelFor: (vid: string) => string | null
  toggleExpand: (personId: string) => void
  fetchRisk: (personId: string) => void
  setPathSource: (personId: string | null) => void
  runPath: (targetId: string) => void
  /** Shortest path between two named people, without the two-click dance. */
  tracePath: (sourceId: string, targetId: string) => void
}
```

to:

```ts
export interface DetailActions {
  select: (selection: Selection | null) => void
  /** Select a vid without the caller having to know whether it's a person or
   * an attribute. */
  openVid: (vid: string) => void
  /** A vid's display label, or null when nothing on screen knows it. */
  labelFor: (vid: string) => string | null
  toggleExpand: (personId: string) => void
  fetchRisk: (personId: string) => void
}
```

- [ ] **Step 2: Strip the path buttons from `PersonDetail.tsx`**

In `apps/web/src/components/explorer/detail/PersonDetail.tsx`, change the `Props` interface from:

```ts
interface Props {
  person: PersonNode
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  pathSource: string | null
  isRoot: boolean
}
```

to:

```ts
interface Props {
  person: PersonNode
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  isRoot: boolean
}
```

Change the function signature from:

```ts
export default function PersonDetail({ person, data, actions, risk, pathSource, isRoot }: Props) {
```

to:

```ts
export default function PersonDetail({ person, data, actions, risk, isRoot }: Props) {
```

Remove this line:

```ts
  const isPathSource = pathSource === person.id
```

In the `chips` block, remove:

```tsx
          {isPathSource && <span className="tag-chip tag-chip--active">path start</span>}
```

In the `actions` block, change:

```tsx
          <button className="btn btn-sm" onClick={() => actions.fetchRisk(person.id)}>
            Risk
          </button>
          {pathSource && pathSource !== person.id ? (
            <button className="btn btn-sm" onClick={() => actions.runPath(person.id)}>
              Path to here
            </button>
          ) : (
            <button
              className="btn btn-sm"
              onClick={() => actions.setPathSource(isPathSource ? null : person.id)}
            >
              {isPathSource ? 'Cancel path' : 'Path from here'}
            </button>
          )}
          <InfoTooltip text="Find the shortest chain of connections between two people. Set a start here, then open another person and pick 'Path to here'." />
```

to:

```tsx
          <button className="btn btn-sm" onClick={() => actions.fetchRisk(person.id)}>
            Risk
          </button>
```

- [ ] **Step 3: Strip the `pathSource` prop from `DetailPanel.tsx`**

In `apps/web/src/components/explorer/detail/DetailPanel.tsx`, change:

```ts
interface Props {
  selection: Selection | null
  network: PersonNetwork | null
  canvasNodes: GraphNode[]
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  pathSource: string | null
}
```

to:

```ts
interface Props {
  selection: Selection | null
  network: PersonNetwork | null
  canvasNodes: GraphNode[]
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
}
```

Change:

```ts
export default function DetailPanel({
  selection,
  network,
  canvasNodes,
  data,
  actions,
  risk,
  pathSource,
}: Props) {
```

to:

```ts
export default function DetailPanel({
  selection,
  network,
  canvasNodes,
  data,
  actions,
  risk,
}: Props) {
```

Change:

```tsx
        <PersonDetail
          key={key}
          person={person}
          data={data}
          actions={actions}
          risk={risk}
          pathSource={pathSource}
          isRoot={person.id === network?.root_id}
        />
```

to:

```tsx
        <PersonDetail
          key={key}
          person={person}
          data={data}
          actions={actions}
          risk={risk}
          isRoot={person.id === network?.root_id}
        />
```

- [ ] **Step 4: Strip the "Trace path between them" button from `LinkDetail.tsx`**

In `apps/web/src/components/explorer/detail/LinkDetail.tsx`, change:

```tsx
      onClose={() => actions.select(null)}
```

Find this larger block:

```tsx
      actions={
        <button
          className="btn btn-sm"
          onClick={() => actions.tracePath(link.source, link.target)}
        >
          Trace path between them
        </button>
      }
      onClose={() => actions.select(null)}
```

and replace it with:

```tsx
      onClose={() => actions.select(null)}
```

(This removes the `actions` prop entirely from the `<DetailShell>` call — it's optional on `DetailShell`, so nothing else needs to change.)

- [ ] **Step 5: Strip the path state/function from `InvestigationPage.tsx`**

In `apps/web/src/pages/InvestigationPage.tsx`, remove the now-unused import:

```ts
import JsonView from '../components/common/JsonView'
```

Remove this state:

```ts
  const [pathSource, setPathSource] = useState<string | null>(null)
  const [pathResult, setPathResult] = useState<unknown>(null)
```

Remove this function entirely:

```ts
  /** `sourceId` defaults to the person the user parked as the path start;
   * a relationship view passes both ends explicitly, since it already knows
   * them and shouldn't make the user pick a start first. */
  async function runShortestPath(targetId: string, sourceId: string | null = pathSource) {
    if (!sourceId) return
    setStatus(`Path ${sourceId} → ${targetId}…`)
    try {
      setPathResult(await api.shortestPath(sourceId, targetId))
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    } finally {
      setPathSource(null)
    }
  }
```

Change the comment above `detailActions` from:

```ts
  // Rebuilt every render on purpose: these close over state the panel has to
  // see fresh (pathSource, the expanded set), and the panel isn't memoized,
  // so a stable identity would buy nothing and could only go stale.
```

to:

```ts
  // Rebuilt every render on purpose: these close over state the panel has to
  // see fresh (the expanded set), and the panel isn't memoized, so a stable
  // identity would buy nothing and could only go stale.
```

Change the `detailActions` object from:

```ts
  const detailActions: DetailActions = {
    select: setSelection,
    openVid,
    labelFor,
    toggleExpand: handleToggle,
    fetchRisk: (personId) => void fetchRisk(personId),
    setPathSource,
    runPath: (targetId) => void runShortestPath(targetId),
    tracePath: (sourceId, targetId) => void runShortestPath(targetId, sourceId),
  }
```

to:

```ts
  const detailActions: DetailActions = {
    select: setSelection,
    openVid,
    labelFor,
    toggleExpand: handleToggle,
    fetchRisk: (personId) => void fetchRisk(personId),
  }
```

Change:

```tsx
          <DetailPanel
            selection={selection}
            network={graph.network}
            canvasNodes={graph.canvasNodes}
            data={detailData}
            actions={detailActions}
            risk={risk}
            pathSource={pathSource}
          />

          {pathResult !== null && (
            <div className="panel">
              <JsonView data={pathResult} title="shortest-path result" />
              <button className="btn" onClick={() => setPathResult(null)}>
                Clear
              </button>
            </div>
          )}
```

to:

```tsx
          <DetailPanel
            selection={selection}
            network={graph.network}
            canvasNodes={graph.canvasNodes}
            data={detailData}
            actions={detailActions}
            risk={risk}
          />
```

Also update the page's top doc comment, which still describes the old flow. Change:

```ts
/** Investigation canvas: search a person, see who they're connected to
 * within 1/2/3 degrees and *why* (the shared phone, address, employer, ...),
 * click any person to fan their own details out in a ring around them, and
 * run shortest-path between two picked people. */
```

to:

```ts
/** Investigation canvas: search a person, see who they're connected to
 * within 1/2/3 degrees and *why* (the shared phone, address, employer, ...),
 * and click any person to fan their own details out in a ring around them.
 * A second mode searches two people by name and finds the strongest chain
 * connecting them directly, without exploring first. */
```

- [ ] **Step 6: Typecheck**

Run: `cd apps/web && npm run build`
Expected: succeeds with no TypeScript errors — this confirms no other file still references `pathSource`/`runPath`/`tracePath`/`setPathSource`.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/pages/InvestigationPage.tsx apps/web/src/components/explorer/detail/PersonDetail.tsx apps/web/src/components/explorer/detail/DetailPanel.tsx apps/web/src/components/explorer/detail/LinkDetail.tsx apps/web/src/components/explorer/detail/detailModel.ts
git commit -m "refactor(web): remove the raw path-from-here/path-to-here flow"
```

---

### Task 7: Wire "Verify connection" mode into the Investigation page

**Files:**
- Modify: `apps/web/src/pages/InvestigationPage.tsx`

**Interfaces:**
- Consumes: `PersonSearchField` (Task 4), `ConnectionChainView` (Task 5), `api.findConnection` (Task 3), `ConnectionResult`/`EntitySearchHit` types, the existing `loadNetwork`/`setRootId`/`setSelection`/`degree` already in this file.
- Produces: the page's `mode` state (`'explore' | 'connect'`) — nothing outside this file depends on it.

- [ ] **Step 1: Add imports**

In `apps/web/src/pages/InvestigationPage.tsx`, add to the existing import block:

```ts
import type { ConnectionResult } from '../api/types'
import ConnectionChainView from '../components/explorer/connection/ConnectionChainView'
import PersonSearchField from '../components/explorer/connection/PersonSearchField'
```

(`EntitySearchHit` is already imported in this file.)

- [ ] **Step 2: Add mode and connection-finder state**

Directly after the existing `const [searchQuery, setSearchQuery] = useState('')` / `searchResults` / `searchError` block, add:

```ts
  const [mode, setMode] = useState<'explore' | 'connect'>('explore')
  const [personA, setPersonA] = useState<EntitySearchHit | null>(null)
  const [personB, setPersonB] = useState<EntitySearchHit | null>(null)
  const [connectionResult, setConnectionResult] = useState<ConnectionResult | null>(null)
  const [connectionLoading, setConnectionLoading] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
```

- [ ] **Step 3: Add the connection-finder handlers**

Directly after the existing `handleSelectResult` function, add:

```ts
  async function handleFindConnection() {
    if (!personA || !personB) return
    setConnectionLoading(true)
    setConnectionError(null)
    setConnectionResult(null)
    try {
      setConnectionResult(await api.findConnection(personA.entity_id, personB.entity_id))
    } catch (err) {
      setConnectionError((err as Error).message)
    } finally {
      setConnectionLoading(false)
    }
  }

  /** The bridge back to Explore mode from a chain-view person card — reuses
   * the same network load Explore's own search result picker triggers. */
  async function handleExploreFromConnection(personId: string) {
    setMode('explore')
    setRootId(personId)
    setSelection({ kind: 'person', id: personId })
    await loadNetwork(personId, degree)
  }
```

- [ ] **Step 4: Add the mode toggle and swap the topbar search area**

Replace the whole topbar block plus the status-strip that follows it — from the opening `<div className="explorer-topbar">` down through the closing of the existing status-strip conditional:

```tsx
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto' }}>
          <strong>Investigation</strong>
        </div>
        <div className="explorer-topbar__search" style={{ position: 'relative' }}>
          <div className="row" style={{ gap: 'var(--space-1)' }}>
            <div className="search-input-wrap">
              <Search className="search-input-wrap__icon" size={14} />
              <input
                className="input input--search"
                placeholder="Search for a person…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <button className="btn btn--primary btn-sm" onClick={handleSearch}>
              Search
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="card search-dropdown">
              {searchResults.map((hit) => (
                <button
                  key={hit.entity_id}
                  className="list-item"
                  onClick={() => handleSelectResult(hit)}
                >
                  <strong>{hit.label || hit.entity_id}</strong>
                  <div className="mono muted">
                    {hit.entity_type} · {hit.entity_id}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="muted">Degree</span>
          <InfoTooltip text="How far apart two people can be. 1 = they share something directly (a phone, an address, an employer). 2 = a friend of a friend. 3 = one step further out." />
          <select
            className="select"
            style={{ width: 110 }}
            value={degree}
            onChange={(e) => handleDegreeChange(Number(e.target.value))}
          >
            <option value={1}>1 degree</option>
            <option value={2}>2 degrees</option>
            <option value={3}>3 degrees</option>
          </select>
        </label>
        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="muted">Min confidence</span>
          <InfoTooltip text="How sure the link has to be before it counts. A value only these two people share scores high; one that forty people share scores near zero. Raising this also hides people you could only reach through a weak link." />
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
            // One request per drag, not one per step.
            onPointerUp={() => {
              if (rootId) void loadNetwork(rootId, degree, { preserveExpanded: true })
            }}
            aria-label="Minimum link confidence"
          />
          <span className="muted" style={{ width: 32 }}>
            {minConfidence.toFixed(2)}
          </span>
        </label>
      </div>

      {(status || searchError || graph.error) && (
        <div className="status-strip">{graph.error ?? searchError ?? status}</div>
      )}
```

with:

```tsx
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto', gap: 'var(--space-2)' }}>
          <strong>Investigation</strong>
          <div className="row" style={{ gap: 'var(--space-1)' }}>
            <button
              className={`btn btn-sm${mode === 'explore' ? ' btn--primary' : ''}`}
              onClick={() => setMode('explore')}
            >
              Explore
            </button>
            <button
              className={`btn btn-sm${mode === 'connect' ? ' btn--primary' : ''}`}
              onClick={() => setMode('connect')}
            >
              Verify connection
            </button>
          </div>
        </div>
        {mode === 'explore' ? (
          <>
            <div className="explorer-topbar__search" style={{ position: 'relative' }}>
              <div className="row" style={{ gap: 'var(--space-1)' }}>
                <div className="search-input-wrap">
                  <Search className="search-input-wrap__icon" size={14} />
                  <input
                    className="input input--search"
                    placeholder="Search for a person…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  />
                </div>
                <button className="btn btn--primary btn-sm" onClick={handleSearch}>
                  Search
                </button>
              </div>
              {searchResults.length > 0 && (
                <div className="card search-dropdown">
                  {searchResults.map((hit) => (
                    <button
                      key={hit.entity_id}
                      className="list-item"
                      onClick={() => handleSelectResult(hit)}
                    >
                      <strong>{hit.label || hit.entity_id}</strong>
                      <div className="mono muted">
                        {hit.entity_type} · {hit.entity_id}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <label className="row" style={{ gap: 'var(--space-2)' }}>
              <span className="muted">Degree</span>
              <InfoTooltip text="How far apart two people can be. 1 = they share something directly (a phone, an address, an employer). 2 = a friend of a friend. 3 = one step further out." />
              <select
                className="select"
                style={{ width: 110 }}
                value={degree}
                onChange={(e) => handleDegreeChange(Number(e.target.value))}
              >
                <option value={1}>1 degree</option>
                <option value={2}>2 degrees</option>
                <option value={3}>3 degrees</option>
              </select>
            </label>
            <label className="row" style={{ gap: 'var(--space-2)' }}>
              <span className="muted">Min confidence</span>
              <InfoTooltip text="How sure the link has to be before it counts. A value only these two people share scores high; one that forty people share scores near zero. Raising this also hides people you could only reach through a weak link." />
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
                // One request per drag, not one per step.
                onPointerUp={() => {
                  if (rootId) void loadNetwork(rootId, degree, { preserveExpanded: true })
                }}
                aria-label="Minimum link confidence"
              />
              <span className="muted" style={{ width: 32 }}>
                {minConfidence.toFixed(2)}
              </span>
            </label>
          </>
        ) : (
          <div className="row" style={{ gap: 'var(--space-3)', flex: 1 }}>
            <PersonSearchField
              label="Person A"
              placeholder="Search for a person…"
              selected={personA}
              onSelect={setPersonA}
            />
            <PersonSearchField
              label="Person B"
              placeholder="Search for a person…"
              selected={personB}
              onSelect={setPersonB}
            />
            <button
              className="btn btn--primary btn-sm"
              disabled={!personA || !personB || connectionLoading}
              onClick={handleFindConnection}
            >
              {connectionLoading ? 'Searching…' : 'Find connection'}
            </button>
          </div>
        )}
      </div>

      {mode === 'explore' && (status || searchError || graph.error) && (
        <div className="status-strip">{graph.error ?? searchError ?? status}</div>
      )}
      {mode === 'connect' && connectionError && <div className="status-strip">{connectionError}</div>}
```

This keeps the Degree/Min-confidence controls scoped to Explore mode — they're meaningless once no single-person network is loaded, and previously would have stayed visible (and functional, misleadingly) in Verify-connection mode if only the search box were swapped.

- [ ] **Step 5: Branch the body between the canvas view and the chain view**

Change the opening of `explorer-body`'s content from:

```tsx
      <div className="explorer-body">
        <div className="explorer-center">
          {view === '2d' ? (
```

to:

```tsx
      <div className="explorer-body">
        {mode === 'connect' ? (
          connectionResult && personA && personB ? (
            <ConnectionChainView
              sourceLabel={personA.label || personA.entity_id}
              targetLabel={personB.label || personB.entity_id}
              result={connectionResult}
              onExplore={(personId) => void handleExploreFromConnection(personId)}
            />
          ) : (
            <div className="panel" style={{ margin: 'var(--space-4)' }}>
              <h3>Verify a connection</h3>
              <p className="text-secondary">
                Pick two people above and choose "Find connection" to see the strongest chain
                linking them — or confirm they aren't connected at all.
              </p>
            </div>
          )
        ) : (
        <div className="explorer-center">
          {view === '2d' ? (
```

Then find the end of the existing two-pane layout — the closing of the `explorer-right` div, immediately before the closing `</div>` of `explorer-body`:

```tsx
        </div>
      </div>
    </main>
  )
}
```

Change it to:

```tsx
        </div>
        )}
      </div>
    </main>
  )
}
```

- [ ] **Step 6: Typecheck**

Run: `cd apps/web && npm run build`
Expected: succeeds with no TypeScript errors, and no unbalanced-JSX errors from the added conditional wrapping (this is the step that will catch a misplaced brace from Steps 4-5 — if it fails, re-check that every `(` opened for a ternary/`&&` in those steps has its matching `)`/closing tag).

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/pages/InvestigationPage.tsx
git commit -m "feat(web): add Verify connection mode to the Investigation page"
```

---

### Task 8: Verify end to end

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run the full backend unit suite**

Run: `cd apps/api && ../../.venv/bin/pytest tests/unit -v`
Expected: PASS, all tests.

- [ ] **Step 2: Run the frontend build and test suite**

Run: `cd apps/web && npm run build && npm run test`
Expected: both succeed — `npm run build` typechecks and bundles, `npm run test` runs the existing vitest suite (this feature adds no new `*.test.ts` files, since its logic is either backend-tested in Task 1 or thin UI verified manually below).

- [ ] **Step 3: Start the stack and verify the golden path in a browser**

Per this repo's `CLAUDE.md`, ask before starting the stack (it's a shared, memory-constrained box). Once running (`./dev`, seeded with `.venv/bin/python scripts/seed_demo_graph.py --space demo_graph` if `demo_graph` is empty):

1. Open the Investigation page, click "Verify connection".
2. Search and pick two people known to be connected in the demo dataset (e.g. via a shared document or field value — check `scripts/seed_demo_graph.py` for a connected pair).
3. Click "Find connection". Confirm the chain view shows both people, the reason chip(s) for each hop, and an overall confidence meter.
4. Click "Explore this person" on one of the chain's people. Confirm it switches back to Explore mode with that person's network loaded.
5. Return to "Verify connection", pick two people with no plausible connection (or a person and an isolated one), click "Find connection", and confirm the "No connection found... within 4 degrees" message appears.
6. Switch back to "Explore" mode and confirm the original single-person search, canvas, and detail panel still work exactly as before (degree/min-confidence controls, clicking a person, clicking a link) — this is the regression check for Task 6's removal.

- [ ] **Step 4: Tear down the stack**

Run: `./dev down`

No commit for this task — it's verification only.
