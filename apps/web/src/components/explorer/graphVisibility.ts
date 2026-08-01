import type { GraphEdge, GraphNode } from '../../api/types'
import { roleForNode } from './graphStyle'

export interface VisibleGraph {
  visibleNodes: GraphNode[]
  visibleEdges: GraphEdge[]
}

/** Investigation's reveal-on-click hierarchy: main nodes (person/company/
 * organization) and edges between two main nodes are always visible. A
 * sub/attribute node (phone, email, address, ...) is visible only once at
 * least one main node it's directly connected to has been "revealed" —
 * every main node, including the initially searched one, starts collapsed,
 * so attribute clutter never appears until the user asks for it. */
export function computeVisibleGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  mainTags: Set<string>,
  revealedVids: Set<string>,
): VisibleGraph {
  const roleByVid = new Map(nodes.map((n) => [n.vid, roleForNode(n, mainTags)]))

  const subVisible = new Set<string>()
  for (const edge of edges) {
    const srcRole = roleByVid.get(edge.src)
    const dstRole = roleByVid.get(edge.dst)
    if (srcRole === 'sub' && dstRole === 'main' && revealedVids.has(edge.dst)) {
      subVisible.add(edge.src)
    }
    if (dstRole === 'sub' && srcRole === 'main' && revealedVids.has(edge.src)) {
      subVisible.add(edge.dst)
    }
  }

  const visibleNodes = nodes.filter((n) => roleByVid.get(n.vid) === 'main' || subVisible.has(n.vid))
  const visibleVids = new Set(visibleNodes.map((n) => n.vid))
  const visibleEdges = edges.filter((e) => visibleVids.has(e.src) && visibleVids.has(e.dst))

  return { visibleNodes, visibleEdges }
}
