import type { GraphEdge, GraphNode } from '../../api/types'

export const TAG_PALETTE = [
  '#2f6feb',
  '#b5720a',
  '#1e8a5f',
  '#a340c9',
  '#c23b32',
  '#0f9bab',
]

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

/** Prefer the human-readable relationship label captured at ingestion
 * (stored as the `relationship_type` edge property) over the raw edge
 * type code, e.g. "childhood friend" instead of "RELATED_TO". */
export function edgeLabel(edge: GraphEdge): string {
  const relationshipType = edge.properties?.relationship_type
  if (typeof relationshipType === 'string' && relationshipType.trim()) return relationshipType
  return edge.edge_type
}
