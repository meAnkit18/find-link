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

## Checks

    npx tsc -b       # type-check
    npm run build    # production build
    npm run lint     # eslint
