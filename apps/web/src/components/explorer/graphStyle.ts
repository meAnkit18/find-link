import type { GraphEdge, GraphNode } from '../../api/types'

// Dark-bg-legible hues (kindred-main's node color language) — hashed onto
// tags below, so any schema's tag set gets a consistent, readable color.
export const TAG_PALETTE = [
  '#818cf8',
  '#fbbf24',
  '#34d399',
  '#f472b6',
  '#f87171',
  '#38bdf8',
]

// Shared accent colors for edges and the selected/hover highlight, used by
// both the 2D (cytoscape) and 3D (Three.js) canvases and the popup card.
export const EDGE_COLOR = '#94a3b8'
export const SELECT_COLOR = '#38bdf8'

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

/** Prefer the human-readable relationship label captured at ingestion
 * (stored as the `relationship_type` edge property) over the raw edge
 * type code, e.g. "childhood friend" instead of "RELATED_TO". */
export function edgeLabel(edge: GraphEdge): string {
  const relationshipType = edge.properties?.relationship_type
  if (typeof relationshipType === 'string' && relationshipType.trim()) return relationshipType
  return edge.edge_type
}
