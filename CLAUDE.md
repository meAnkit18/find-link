# CLAUDE.md

## Running the stack

The full stack does run on this machine — verified 2026-08-07. Ask before
starting it, since it's a shared box and NebulaGraph is memory-hungry, and
tear it down when you're done.

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
- Space `intel_kg_v2` persists in Docker volumes across runs, so there is
  real data to test against; don't assume an empty graph.
- Frontend-only is still fine for pure UI work and needs none of the above.

Note: `origin` is configured over HTTPS with no credential helper, so a plain `git push` fails here. There's a working SSH deploy key at `~/ankit_kumar/github_connect/ankit_kumar` (pub key registered to meAnkit18) — push with:
`GIT_SSH_COMMAND="ssh -i ~/ankit_kumar/github_connect/ankit_kumar -o IdentitiesOnly=yes" git push git@github.com:meAnkit18/find-link.git main`

## Core Principles

* Think before making changes.
* Prefer correctness over speed.
* Keep changes as small as possible.
