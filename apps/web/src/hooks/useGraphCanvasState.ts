import { useCallback, useRef, useState } from 'react'
import type { GraphEdge, GraphNode } from '../api/types'

function edgeKey(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

interface GraphCanvasState {
  nodes: Map<string, GraphNode>
  edges: Map<string, GraphEdge>
}

function emptyState(): GraphCanvasState {
  return { nodes: new Map(), edges: new Map() }
}

/** Shared node/edge bookkeeping for an incrementally-expandable Cytoscape
 * graph: tracks which nodes are "roots" (the initial view — never pruned by
 * collapse) and which expansions each edge came from, so collapsing one
 * node only removes an edge once no remaining expanded node still needs it
 * (an edge two overlapping expansions both returned survives until both are
 * collapsed), and never drops a node another expansion still references. */
export function useGraphCanvasState() {
  const rootVidsRef = useRef<Set<string>>(new Set())
  // edge key -> set of vids whose expansion returned this edge (an edge can
  // have more than one owner when overlapping expansions both include it)
  const edgeOwnersRef = useRef<Map<string, Set<string>>>(new Map())
  const [state, setState] = useState<GraphCanvasState>(emptyState)

  const setOverview = useCallback((nodes: GraphNode[], edges: GraphEdge[]) => {
    rootVidsRef.current = new Set(nodes.map((n) => n.vid))
    edgeOwnersRef.current = new Map()
    setState({
      nodes: new Map(nodes.map((n) => [n.vid, n])),
      edges: new Map(edges.map((e) => [edgeKey(e), e])),
    })
  }, [])

  const mergeExpansion = useCallback((vid: string, newNodes: GraphNode[], newEdges: GraphEdge[]) => {
    setState((prev) => {
      const nodes = new Map(prev.nodes)
      newNodes.forEach((n) => {
        if (!nodes.has(n.vid)) nodes.set(n.vid, n)
      })
      const edges = new Map(prev.edges)
      newEdges.forEach((e) => {
        const key = edgeKey(e)
        edges.set(key, e)
        const owners = edgeOwnersRef.current.get(key) ?? new Set<string>()
        owners.add(vid)
        edgeOwnersRef.current.set(key, owners)
      })
      return { nodes, edges }
    })
  }, [])

  const collapse = useCallback((vid: string) => {
    setState((prev) => {
      const edges = new Map(prev.edges)
      for (const [key, owners] of edgeOwnersRef.current) {
        if (!owners.has(vid)) continue
        owners.delete(vid)
        if (owners.size === 0) {
          edges.delete(key)
          edgeOwnersRef.current.delete(key)
        }
      }
      const stillReferenced = new Set<string>()
      for (const edge of edges.values()) {
        stillReferenced.add(edge.src)
        stillReferenced.add(edge.dst)
      }
      const nodes = new Map(prev.nodes)
      for (const nodeVid of prev.nodes.keys()) {
        if (nodeVid === vid) continue
        if (rootVidsRef.current.has(nodeVid)) continue
        if (stillReferenced.has(nodeVid)) continue
        nodes.delete(nodeVid)
      }
      return { nodes, edges }
    })
  }, [])

  const addNode = useCallback((node: GraphNode) => {
    setState((prev) => {
      if (prev.nodes.has(node.vid)) return prev
      return { nodes: new Map(prev.nodes).set(node.vid, node), edges: prev.edges }
    })
  }, [])

  const reset = useCallback(() => {
    rootVidsRef.current = new Set()
    edgeOwnersRef.current = new Map()
    setState(emptyState())
  }, [])

  return { ...state, setOverview, mergeExpansion, collapse, addNode, reset }
}
