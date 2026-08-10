# Verify/find connection between two people — design

## Goal

An investigator often starts from a specific question: *are these two named
people connected, and if so, why?* Today the Investigation page only answers
that by searching one person, exploring their network by degree, and hoping
the second person turns up on the canvas (or using the "Path from here" /
"Path to here" flow, which requires both people to already be on screen and
dumps a raw, storage-level JSON blob with no confidence or plain-language
reason).

This adds a direct answer: search two people by name, and see either the
strongest chain connecting them — each hop's reason and confidence, in the
same language the rest of the page already uses — or a clear "not connected"
result.

## Backend

### `PersonNetworkService.find_connection`

New method in `apps/api/src/graph_explorer_api/services/person_network_service.py`:

```python
def find_connection(
    self, source_id: str, target_id: str, max_degree: int = 4
) -> dict | None:
```

Behavior:

1. Fetch both vertices. Return `None` if `source_id` isn't a `person` (the
   router turns this into 404, consistent with `person_network`).
2. If `target_id` isn't a `person` vertex, or `target_id == source_id`,
   return an error payload the router turns into a 400
   (`{"error": "target_not_found"}` / `{"error": "same_person"}`).
3. Run the **existing** `person_network(source_id, degree=max_degree,
   min_confidence=0.0)` BFS unchanged — same reasons/confidence machinery
   already used for exploration. `max_degree` defaults to 4: one hop past the
   UI's existing exploration cap of 3, since a deliberate "are these two
   connected" question can afford to look slightly further than casual
   browsing. Not user-adjustable in the UI.
4. If `target_id` is not among the returned `persons`, respond:
   ```json
   { "connected": false, "source_id": "...", "target_id": "...", "max_degree_searched": 4 }
   ```
5. Otherwise, find the **strongest** path from `source_id` to `target_id`
   over the projected link graph `person_network` just built (see
   *Strongest-path algorithm* below), and respond:
   ```json
   {
     "connected": true,
     "source_id": "...",
     "target_id": "...",
     "path": {
       "persons": [PersonNode, ...],   // source ... target, in hop order
       "links":   [PersonLink, ...],   // one per hop, same shape as person_network's links
       "confidence": 0.42              // combined confidence across the whole chain
     }
   }
   ```
   `PersonNode` / `PersonLink` are the exact same shapes `person_network`
   already returns — no new serialization format.

### Strongest-path algorithm

"Strongest" = the path maximizing the product of each hop's `confidence`
(independent hops compound the same way independent reasons on one hop
already do via `combine`), ties broken by fewest hops.

Implemented as Dijkstra over the finalized `links` from step 3, with edge
weight `-log(confidence)` (minimizing sum of weights == maximizing the
product). Priority tuple is `(weight_sum, hop_count)` so equal-weight paths
prefer fewer hops. `confidence` is always `> 0` for a link that was actually
emitted (a link requires `owner_count >= 2`, so `rarity() > 0`, and every
`weight_for()` entry, including the default, is `> 0`) — no `log(0)` guard
needed, but the implementation clamps defensively (`max(confidence, 1e-9)`)
rather than assuming that invariant holds forever.

Runs against the graph already built in memory by `person_network` — no
extra graph queries.

### Router

New endpoint in `apps/api/src/graph_explorer_api/routers/entities.py`, next
to `person-network`:

```
GET /api/entities/{entity_id}/connection/{target_id}
```

No query parameters beyond the path — `max_degree` is fixed at 4 and not
exposed, matching the "not user-adjustable" decision.

The existing `GET /api/entities/shortest-path` (raw storage-hop traversal,
no confidence) is untouched: it continues to back the developer-facing forms
on the Entities/Risk page, Agent Tools page, and API Console page.

## Frontend

### Mode toggle

`InvestigationPage.tsx` gains a segmented control in the topbar: **Explore**
/ **Verify connection**. `Explore` is today's existing single-person search,
canvas, and detail panel — unchanged. `Verify connection` is new.

### Verify connection mode

Topbar search area swaps for two independent person-search inputs (Person A
/ Person B — same type-and-pick UX as the existing search box, duplicated)
plus a "Find connection" button, enabled once both are picked.

The canvas + detail-panel split underneath is replaced by a new full-width
component, `ConnectionChainView` (new file,
`apps/web/src/components/explorer/connection/ConnectionChainView.tsx`):

- **Connected**: a horizontal chain of person cards, each consecutive pair
  joined by the reason chip(s) for that hop. Reuses `describeVia` /
  `ReasonCard` from `detailModel.ts` / `ReasonCard.tsx` unchanged, so a hop
  reads exactly like an entry in the existing "Connections" tab. An overall
  confidence badge (using the existing `confidenceLabel`/`confidenceTone`
  helpers) sits at the top of the chain. Each person card carries a small
  "Explore this person" action that switches back to `Explore` mode rooted
  at that person, via the existing `loadNetwork` — a low-cost bridge between
  the two modes.
- **Not connected**: a plain message — "No connection found between \<A\>
  and \<B\> within 4 degrees of separation."
- **Loading / error**: reuses the page's existing `status-strip` pattern.

### API client / types

`apps/web/src/api/client.ts`:
```ts
findConnection: (sourceId: string, targetId: string) =>
  request<ConnectionResult>(
    `/api/entities/${encodeURIComponent(sourceId)}/connection/${encodeURIComponent(targetId)}`,
  ),
```

`apps/web/src/api/types.ts`:
```ts
export type ConnectionResult =
  | { connected: false; source_id: string; target_id: string; max_degree_searched: number }
  | {
      connected: true
      source_id: string
      target_id: string
      path: { persons: PersonNode[]; links: PersonLink[]; confidence: number }
    }
```

### Removed

The "Path from here" / "Path to here" flow, now superseded:

- `InvestigationPage.tsx`: `pathSource`, `pathResult` state, `runShortestPath`,
  the `JsonView` block that dumped the raw result.
- `PersonDetail.tsx`: the "Path from here" / "Path to here" / "Cancel path"
  buttons and their `InfoTooltip`, and the `isPathSource` chip.
- `detailModel.ts`: `setPathSource` / `runPath` / `tracePath` removed from
  `DetailActions`.
- `DetailPanel.tsx` / callers: the `pathSource` prop removed from the chain.

`api.shortestPath` itself (the client method) and the backend
`/api/entities/shortest-path` endpoint are **not** removed — they still back
the Entities/Risk page, Agent Tools page, and API Console page.

## Testing

- Backend: unit tests for `find_connection` against the demo graph fixture
  already used by existing `person_network_service` tests — a known-connected
  pair (asserting the returned chain's hop count, confidence, and reason
  kinds), a known-unconnected pair, a nonexistent target, and
  `source_id == target_id`.
- Frontend: a `connectionModel`-level test if any new pure logic is
  extracted (unlikely — this reuses `describeVia` as-is); otherwise manual
  verification in the browser per this project's UI-change convention (start
  the dev stack, exercise the golden path and the "not connected" path).

## Out of scope (YAGNI)

- Surfacing multiple distinct connecting paths — only the single strongest
  chain is returned.
- A user-adjustable search-depth control for this flow.
- Highlighting the path on the graph canvas — the chain view is standalone,
  not canvas-integrated.
