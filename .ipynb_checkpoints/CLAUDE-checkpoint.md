# CLAUDE.md

## Core Principles

* Think before making changes.
* Prefer correctness over speed.
* Keep changes as small as possible.
* Preserve existing behavior unless the task requires otherwise.
* Ask for clarification only when requirements are genuinely ambiguous or when a decision would permanently affect the public API or architecture.

---

## Planning

For non-trivial tasks:

1. Briefly restate your understanding.
2. State any important assumptions.
3. If multiple good approaches exist, explain the trade-offs and recommend one.
4. For larger tasks, provide a short implementation plan before coding.

Keep this concise.

---

## Scope

Only implement what was requested.

Unless explicitly asked:

* Do not add dependencies.
* Do not change database schemas or migrations.
* Do not modify public APIs.
* Do not introduce fallback behavior.
* Do not perform unrelated refactoring.
* Do not rename or reorganize files.

Prefer modifying existing files over creating new ones.

Every change should directly support the requested task.

---

## Code Quality

* Match the existing architecture and coding style.
* Reuse existing abstractions before creating new ones.
* Keep solutions simple and maintainable.
* Remove only code made unnecessary by your changes.
* Avoid speculative features.

If you discover a significantly better approach:

1. Explain why.
2. Compare it with the requested approach.
3. Wait for approval before implementing an alternative design.

Challenge incorrect technical assumptions instead of agreeing automatically.

---

## Investigation Mode

When asked to investigate, analyze, review, or evaluate:

* Do not modify code.
* Do not implement anything.
* Do not change the database.
* Diagnose the problem.
* Explain root causes.
* Identify affected components.
* Describe risks, dependencies, and possible solutions.

---

## Verification

Before considering work complete:

* Perform the smallest appropriate verification.
* Run relevant tests when available.
* If verification cannot be performed, clearly explain why.
* Never claim success without verification.

---

## Graphify

Use the Graphify skill whenever it provides a clear benefit.

Prefer Graphify for:

* Understanding project architecture
* Tracing execution flow
* Exploring dependencies
* Finding references
* Following call chains
* Understanding data flow
* Investigating unfamiliar code

For small, localized edits, read only the relevant files instead.

---

## Documentation

For significant features or architectural changes:

* Update the relevant documentation.
* Record why the decision was made, not just what changed.
* Document important assumptions, trade-offs, and limitations.
* Prefer updating existing documentation instead of creating duplicates.

---
