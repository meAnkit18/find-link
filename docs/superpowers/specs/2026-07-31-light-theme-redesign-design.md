# FindLink light theme & UX redesign

## Goal

FindLink's frontend (`apps/web`) is currently a dark, dense "testing workbench" theme built for engineers. Redesign it into a clean, modern light theme that a non-technical investigator can use confidently, with an ⓘ tooltip beside every button, input, and important field explaining it in plain English. Presentation-layer only — no changes to data, API contracts, or workflow structure.

## Scope

All 8 sections get the same treatment: Graphs, Ingest, Investigation, Cases, Entities & Risk, Review Queue, Agent Tools, API Console. The last two are more technical but still get the full light/simple/tooltip treatment (not a separate style).

Depth: visual + light UX polish. Keep each page's existing layout, fields, and workflow steps. No restructuring, no hiding fields behind "Advanced" toggles, no reordering steps.

## Visual system

- Canvas `#f6f7f9`. Cards: white, `1px solid #e6e9ee`, `border-radius: 14px`, shadow `0 1px 2px rgba(20,20,43,.04)`.
- Accent: blue `#2f6feb` (hover `#2557c7`) — primary buttons, active nav, links, ⓘ icon fill.
- Status colors (risk levels, match scores), reused via a `Badge` component:
  - low/strong: text `#1e8a5f` on `#e9f9f0`
  - medium: text `#b5720a` on `#fff4e5`
  - high/weak: text `#c23b32` on `#fdeceb`
- Typography: keep the existing Inter/system-ui stack from `tokens.css`, retuned for light backgrounds. Body 13px, labels 12.5px, headings 20-24px.
- Spacing/radius scale carried over from `tokens.css` (4/8/12/16/24/32 spacing; 6/10/14 radii).

## Shell & navigation

Replace the top nav bar in `App.tsx` with a left sidebar (180px wide): logo + "FindLink" wordmark, then the 6 investigator pages, a divider, then Agent Tools / API Console (styled slightly muted to signal "technical"). Active item is a solid blue pill; inactive items are gray text with a subtle hover background.

## Component inventory

Build once in `components/common/`, reuse everywhere, replacing ad hoc styling in `index.css` (754 lines) and inline styles scattered across pages:

- `Button` — primary (blue), secondary (ghost/outline), danger variants
- `Input` / `Select` — white fill, 1px border, blue focus ring
- `Card` — the white panel described above
- `Badge` — risk/status pills using the status colors above
- `Table` — light header row, hairline row dividers, hover highlight
- `EmptyState` — icon + short plain-English message + optional action
- `Spinner` / loading skeleton row
- `InfoTooltip` — the ⓘ component (see below)

## Tooltip system

`InfoTooltip`: small circular ⓘ, blue-on-light-blue fill, hover reveals a dark popover with one short plain-English sentence (no jargon, doesn't just restate the field name).

Applied beside:
- every button whose action isn't self-evident from its label
- every input/select/field
- every "important field" — data whose meaning a non-technical user could misread (match confidence, risk score, entity resolution status, job/queue status, graph density, etc.)

Not applied to page titles or purely decorative labels. Per-page tooltip copy is drafted during implementation (page by page), not enumerated here.

## Graph canvas re-theming

`components/explorer/GraphCanvas.tsx` (Cytoscape.js) currently assumes a dark background. Needs: light background, lighter grid/edge colors, and node colors that stay readable on white. This is the one piece with real technical risk in an otherwise CSS/markup-level redesign.

## Out of scope

- No changes to API calls, data shapes, routing structure, or business logic.
- No workflow simplification (collapsing steps, hiding advanced fields) — visual/UX polish only.
- No changes to the backend (`apps/api`, `apps/worker`) or infra.
