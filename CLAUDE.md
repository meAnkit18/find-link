# CLAUDE.md

## Running the stack

The full stack does run on this machine — verified 2026-08-07. Ask before
starting it, since it's a shared box and NebulaGraph is memory-hungry, and
tear it down when you're done.

    ./dev            # NebulaGraph + API + web, backgrounded
    ./dev down       # stop all three (graph data kept)
    ./dev status     # what's running
    ./dev logs api   # or web / graph; add -f to follow

`./dev` waits for each layer before starting the next and prints where the
logs went; it wraps the manual sequence, which is still:

    cd deploy && docker compose up -d     # NebulaGraph; wait for healthy
    # the `console` service is a one-shot ADD HOSTS job — wait for
    # "Storage host registered" in its log before the API can create a space
    .venv/bin/uvicorn graph_explorer_api.main:app --port 8000 --app-dir apps/api/src
    cd apps/web && npm run dev            # proxies /api to :8000

Notes:

- The compose file lives in `deploy/`. The root README and
  `packages/graph-core/README.md` tell you it's at the repo root or in
  `packages/graph-core/` — both are wrong.
- Memory is the real constraint: the containers cap at ~1.4GB combined, and
  this box usually has well under 1GB genuinely free, so it leans on swap.
  Check `free -h` first and prefer `docker compose down` (without `-v`) when
  you're finished — `-v` wipes the ingested graph data.
- Spaces persist in Docker volumes across runs, but they are close to empty
  — as of 2026-08-08, `intel_kg_v2` has no people at all, and
  `intelligence_graph` (the space the API actually uses by default, via
  `NEBULA_SPACE`) has 2 people and 0 documents. Don't assume there is real
  data to test against: anything that needs a populated graph needs seeding
  first, and a "it works against live data" check on this box proves very
  little.
- Frontend-only is still fine for pure UI work and needs none of the above.

Note: `origin` is configured over HTTPS with no credential helper, so a plain `git push` fails here. There's a working SSH deploy key at `~/ankit_kumar/github_connect/ankit_kumar` (pub key registered to meAnkit18) — push with:
`GIT_SSH_COMMAND="ssh -i ~/ankit_kumar/github_connect/ankit_kumar -o IdentitiesOnly=yes" git push git@github.com:meAnkit18/find-link.git main`

## Core Principles

* Think before making changes.
* Prefer correctness over speed.
* Keep changes as small as possible.
