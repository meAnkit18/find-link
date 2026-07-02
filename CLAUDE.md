# CLAUDE.md

# Core Principles

* Think before coding.
* Ask questions instead of making assumptions.
* Prefer correctness over speed.
* Keep solutions simple.
* Make the smallest change that solves the problem.
* Never silently change behavior.

---

# Before Implementing

1. Briefly restate your understanding of the task.
2. State any assumptions.
3. If requirements are unclear or multiple interpretations exist, stop and ask.
4. If there are multiple good solutions, explain the trade-offs and recommend one.
5. For simple tasks, keep explanations short. For complex tasks, provide a concise implementation plan before coding.

---

# Implementation

* Implement only what was requested.
* Match the existing architecture and coding style.
* Prefer modifying existing files over creating new ones.
* Avoid unnecessary abstractions.
* Avoid premature optimization.
* Avoid speculative features.
* Avoid unrelated refactoring.
* Do not rename or reorganize files unless required.
* Remove only code made unnecessary by your own changes.

Every changed line should directly support the requested task.

---

# Creativity

Be creative during:

* Architecture
* System design
* Algorithms
* Debugging
* Performance optimization
* Developer experience
* Feature design

If you discover a significantly better solution:

* Explain it.
* Compare it with the requested approach.
* Recommend one with reasoning.

Do not implement alternative designs without my approval.

Challenge my ideas when there is a technically better approach. Do not agree simply because I suggested something.

---

# Investigation Mode

When I ask you to investigate, analyze, or evaluate:

* Do not modify code.
* Do not modify the database.
* Do not implement anything.
* Diagnose the problem.
* Explain root causes.
* Explain affected areas.
* Describe risks, dependencies, and possible solutions.

---

# Stability

Unless explicitly requested:

* Do not add dependencies.
* Do not change database schemas or migrations.
* Do not modify public APIs.
* Do not introduce fallback mechanisms.
* Do not make unrelated improvements.

Existing functionality must continue to work.

---

# Verification

Before considering a task complete:

* Perform the smallest appropriate verification.
* Run relevant tests if available.
* If verification cannot be performed, clearly explain why.
* Never claim success without verification.

---

# Efficiency

Be mindful of token usage.

* Keep responses concise unless detailed reasoning is requested.
* Avoid repeating information.
* Read only the files necessary for the task.
* Do not scan the entire repository unless required.
* Prefer focused, incremental changes.
* Avoid unnecessary tool usage.
* Avoid long explanations for simple tasks.

Optimize for correctness with minimal token usage.

---

# Graphify

Use the Graphify skill whenever it provides a clear benefit.

Prefer Graphify for:

* Understanding project architecture
* Tracing execution flow
* Exploring dependencies
* Finding references
* Following call chains
* Understanding data flow
* Investigating unfamiliar code

For simple edits, reading the relevant files directly is preferred.

---

# Documentation

Maintain project documentation as the project evolves.

For significant features or architectural changes:

* Update the relevant documentation.
* Explain **why** the decision was made, not only **what** changed.
* Record assumptions, trade-offs, limitations, and design decisions.
* Keep documentation synchronized with the code.
* Prefer updating existing documentation over creating duplicates.

Documentation should help future development sessions quickly understand the system and the reasoning behind previous decisions.

---

# Git Workflow

After completing and verifying a task:

1. Review the changed files.
2. Ensure no unrelated files are included.
3. Create a clear, descriptive commit.
4. Push the commit to the current branch.

Do not commit:

* temporary files
* build artifacts
* logs
* secrets
* environment files
* unrelated changes

If verification fails or the push encounters conflicts, stop and explain the issue.

---

# Deployment Environment

The application runs on a remote EC2 instance.

Your responsibility ends after producing verified code, committing it, and pushing it to GitHub.

Do not:

* SSH into the EC2 instance
* Deploy the application
* Restart services
* Modify Nginx
* Modify systemd
* Run Docker containers
* Run docker-compose
* Start long-running development servers

I will:

1. Pull the latest changes on the EC2 server.
2. Start or restart the application.
3. Verify it in the deployment environment.

---

# Working Style

When possible:

* Keep diffs small.
* Preserve existing behavior.
* Prefer existing project patterns.
* Ask instead of guessing.
* Explain important engineering decisions briefly.
* Leave the project cleaner only where directly related to the requested task.


## Decision Making

Make reasonable engineering decisions independently.

Do not interrupt implementation for routine architectural questions.

Only ask for clarification if:
- the requirements are ambiguous,
- a decision would permanently affect the public API,
- or multiple choices have significantly different long-term consequences.

Otherwise:
- choose the best approach,
- document why,
- and continue implementation.

## Development Environment

This repository is developed on a remote machine that does not run the application.

Do not start databases, Docker containers, or infrastructure automatically.

Do not require NebulaGraph to be available while implementing the code.

Focus on producing clean, production-ready code and architecture only.

Runtime validation and integration testing will be performed later on the local development environment.
