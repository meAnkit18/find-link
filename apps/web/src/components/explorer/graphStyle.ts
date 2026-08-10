import type { GraphEdge, GraphNode } from '../../api/types'

// Mid-saturation hues that read clearly against a light canvas — hashed
// onto tags below, so any schema's tag set gets a consistent, readable
// color.
export const TAG_PALETTE = [
  '#6366f1',
  '#d97706',
  '#059669',
  '#db2777',
  '#dc2626',
  '#0284c7',
]

// Shared accent colors for edges and the selected/hover highlight, used by
// both the 2D (cytoscape) and 3D (Three.js) canvases and the popup card.
export const EDGE_COLOR = '#64748b'
export const SELECT_COLOR = '#0ea5e9'

// The searched node — the root the rest of the graph hangs off. Kept
// distinct from SELECT_COLOR on purpose: selection moves with every click,
// while this marks one node for as long as the search stands, so the two
// have to be tellable apart when they land on the same node. Brighter than
// the palette's amber (#d97706) so a ring around a document still reads.
export const ROOT_COLOR = '#f59e0b'

// How many connections away from the searched person. Violet / teal /
// crimson for 1st / 2nd / 3rd degree.
//
// Validated with the dataviz skill's checker against the canvas surface
// (#f2f4f7, light): worst all-pairs colorblind separation is ΔE 14.8 —
// comfortably past the 8.0 target — and all three clear the 3:1 contrast
// floor, so a 3rd-degree arrow is as legible as a 1st-degree one. Do not
// swap a hue here without re-running that check; a plausible-looking
// alternative (indigo/teal/fuchsia) failed at ΔE 4.4 under protanopia.
export const DEGREE_PALETTE = ['#7c3aed', '#0d9488', '#9f1239']

/** Color for a 1st/2nd/3rd degree connection, or null for anything that
 * isn't one — degree 0 (the root itself), attribute sub-nodes, and every
 * node on the Explorer page, which has no notion of degree at all. Those
 * keep their tag color. Degrees past the palette clamp to the last step
 * rather than wrapping, so a deeper network can't recycle 1st-degree
 * violet for the most distant people. */
export function colorForDegree(degree: number | null): string | null {
  if (degree === null || !Number.isFinite(degree) || degree < 1) return null
  return DEGREE_PALETTE[Math.min(Math.round(degree), DEGREE_PALETTE.length) - 1]
}

/** The degree a node carries, or null if it has none. Investigation's
 * person projection stamps this onto every person it returns. */
export function nodeDegree(node: GraphNode): number | null {
  const degree = Number(node.properties?.degree)
  return Number.isFinite(degree) ? degree : null
}

/** The degree a link was discovered at, or null for a link that has none —
 * notably the person-to-attribute spokes, which are structure rather than
 * a connection at any distance. */
export function edgeDegree(edge: GraphEdge): number | null {
  const degree = Number(edge.properties?.degree)
  return Number.isFinite(degree) ? degree : null
}

/** Whether this node/edge arrived with the most recent filter change —
 * raising the degree, or relaxing the confidence threshold. Set by
 * Investigation's data layer, absent everywhere else. Cleared on a new
 * search, because then everything is new and marking it says nothing. */
export function isNewSinceFilterChange(el: {
  properties?: Record<string, unknown> | null
}): boolean {
  return el.properties?.is_new === true
}

export function colorForTag(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  return TAG_PALETTE[hash % TAG_PALETTE.length]
}

export function edgeId(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

export type NodeRole = 'main' | 'sub'

/** A node is a "main" hub if `mainTags` is empty (no hierarchy configured —
 * every node renders uniformly) or if it carries at least one of the
 * configured main tags; everything else is a "sub"/attribute node. */
export function roleForNode(node: GraphNode, mainTags: Set<string>): NodeRole {
  if (mainTags.size === 0) return 'main'
  return node.tags.some((t) => mainTags.has(t)) ? 'main' : 'sub'
}

/** How many separate things this edge represents. Investigation's projected
 * person links set `via_count` (two people can share a phone *and* an
 * address); everything else is a single relationship, weight 1. */
export function edgeWeight(edge: GraphEdge): number {
  const count = Number(edge.properties?.via_count)
  return Number.isFinite(count) && count > 0 ? count : 1
}

/** How confident the projection is in this link, 0-1. Investigation's
 * person links carry it; anything else is treated as certain, because a
 * stored edge is an assertion rather than an inference. */
export function edgeConfidence(edge: GraphEdge): number {
  const confidence = Number(edge.properties?.confidence)
  return Number.isFinite(confidence) ? Math.min(1, Math.max(0, confidence)) : 1
}

/** Prefer the human-readable relationship label captured at ingestion
 * (stored as the `relationship_type` edge property) over the raw edge
 * type code, e.g. "childhood friend" instead of "RELATED_TO". */
export function edgeLabel(edge: GraphEdge): string {
  const relationshipType = edge.properties?.relationship_type
  if (typeof relationshipType === 'string' && relationshipType.trim()) return relationshipType
  return edge.edge_type
}
