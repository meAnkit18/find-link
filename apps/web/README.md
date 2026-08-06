# graph-explorer-web

Vite + React + TypeScript frontend for the Graph Explorer app. Talks only
to `graph-explorer-api`'s REST endpoints — no NebulaGraph/graph-core
knowledge here.

## Install & run

    npm install
    npm run dev

Requires `graph-explorer-api` running on `http://localhost:8000` (see
`apps/api/README.md`); `vite.config.ts` proxies `/api/*` to it in dev, so
no CORS configuration is needed locally. For a production deploy against a
different origin, set `VITE_API_BASE_URL`.

## Stack

- **Cytoscape.js** (+ `cytoscape-fcose` layout), driven imperatively via a
  ref rather than a declarative React wrapper — expand/collapse needs
  incremental add/remove of canvas elements while preserving existing node
  positions, which a declarative wrapper fights.
- **TanStack Query** for server state (search, node/neighbor fetches,
  import-job polling).
- **Zustand** for canvas UI state (selection, expanded-node set, active
  filters) — shared across sibling components (search bar, canvas, detail
  panel, filter panel) without prop-drilling.
- **react-router-dom** for the three views: graphs list → upload →
  explorer.
- Plain CSS (see `src/index.css` / `src/styles/tokens.css`) — no Tailwind
  toolchain.

## The Investigation page

Unlike Explorer, which renders whatever is in the graph, Investigation is
**person-centric**: people are the only primary nodes.

The graph stores a person's phone/email/address/passport/employer as
separate vertices hanging off the person, so two people who share a phone
are two hops apart with no edge between them. Investigation therefore
renders a *projection* served by `GET /api/entities/{id}/person-network`,
where a link means "these two share something" and carries the shared thing
along as its reason. The **Degree** control (1/2/3) counts those
connections, not stored hops: 1 is a direct share, 2 a friend of a friend,
3 one step further.

Clicking a person fans their own details out in a ring around them
(`GET /api/entities/{id}/attributes`). Those attribute nodes are placed by
`components/explorer/radialLayout.ts` and handed to the canvas as
`pinnedPositions` — they're locked and excluded from the fcose run, so
adding one doesn't reshuffle the people. An attribute two expanded people
share sits between them, since it's the reason they're linked.

`GraphCanvas`'s `pinnedPositions` / `onParentMoved` / `onPositionsSettled`
props are all optional; Explorer passes none of them and behaves exactly as
before.

## Checks

    npx tsc -b       # type-check
    npm run build    # production build
    npm run lint     # eslint
