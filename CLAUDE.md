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
- **The space the API uses comes from `.env`, not the process environment.**
  `main.py` calls `load_dotenv(override=True)`, so `NEBULA_SPACE=... ./dev`
  is silently ignored — edit `.env` instead. Standalone scripts under
  `scripts/` do *not* load `.env`, so they fall back to the
  `intelligence_graph` default and will happily talk to a different space
  than the running API unless you pass `--space`.
- Spaces persist in Docker volumes across runs, but they start empty.
  `demo_graph` is the working dataset; seed or re-seed it with:

      .venv/bin/python scripts/seed_demo_graph.py --space demo_graph

  It is idempotent (fixed vids, INSERT overwrites), and it writes through
  the same GraphWriter calls ingestion makes, so what lands is what real
  ingestion would produce — including the field-value index the person
  projection walks. `scripts/reindex_field_values.py` rebuilds just that
  index when the matching rules change.
- `test_evidence_pipeline_e2e.py` writes to the real NebulaGraph, so running
  the suite can leave residue in whatever space `.env` points at.
- Frontend-only is still fine for pure UI work and needs none of the above.

Note: `origin` is configured over HTTPS with no credential helper, so a plain `git push` fails here. There's a working SSH deploy key at `~/ankit_kumar/github_connect/ankit_kumar` (pub key registered to meAnkit18) — push with:
`GIT_SSH_COMMAND="ssh -i ~/ankit_kumar/github_connect/ankit_kumar -o IdentitiesOnly=yes" git push git@github.com:meAnkit18/find-link.git main`

## Core Principles

* Think before making changes.
* Prefer correctness over speed.
* Keep changes as small as possible.
