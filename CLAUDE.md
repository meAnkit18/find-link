# CLAUDE.md

Important: Do not run the complete project, NebulaGraph, backend, or Docker services on the EC2 instance. The EC2 machine is only for editing the code and doesn't have enough resources to run the full stack. Only make the required code changes. If you need to verify the UI, you may run the frontend only. I will pull the updated code and run the entire project (including NebulaGraph and the backend) on my local machine for testing.

Note: `origin` is configured over HTTPS with no credential helper, so a plain `git push` fails here. There's a working SSH deploy key at `~/ankit_kumar/github_connect/ankit_kumar` (pub key registered to meAnkit18) — push with:
`GIT_SSH_COMMAND="ssh -i ~/ankit_kumar/github_connect/ankit_kumar -o IdentitiesOnly=yes" git push git@github.com:meAnkit18/find-link.git main`

## Core Principles

* Think before making changes.
* Prefer correctness over speed.
* Keep changes as small as possible.
