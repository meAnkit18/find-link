import { useCallback, useRef, useState } from 'react'
import type { GraphEdge, GraphNode } from '../api/types'

function edgeKey(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

interface GraphCanvasState {
  nodes: Map<string, GraphNode>
  edges: Map<string, GraphEdge>
}

const EMPTY_STATE: GraphCanvasState = { nodes: new Map(), edges: new Map() }

/** Shared node/edge bookkeeping for an incrementally-expandable Cytoscape
 * graph: tracks which nodes are "roots" (the initial view — never pruned by
 * collapse) and which edges each expansion added, so collapsing one node
 * only removes *its* edges, not ones another still-expanded node also
 * needs, and never drops a node another expansion still references. */
export function useGraphCanvasState() {
  const rootVidsRef = useRef<Set<string>>(new Set())
  const expansionEdgeKeysRef = useRef<Map<string, Set<string>>>(new Map())
  const [state, setState] = useState<GraphCanvasState>(EMPTY_STATE)

  const setOverview = useCallback((nodes: GraphNode[], edges: GraphEdge[]) => {
    rootVidsRef.current = new Set(nodes.map((n) => n.vid))
    expansionEdgeKeysRef.current = new Map()
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
      const addedKeys = expansionEdgeKeysRef.current.get(vid) ?? new Set<string>()
      newEdges.forEach((e) => {
        const key = edgeKey(e)
        if (!edges.has(key)) addedKeys.add(key)
        edges.set(key, e)
      })
      expansionEdgeKeysRef.current.set(vid, addedKeys)
      return { nodes, edges }
    })
  }, [])

  const collapse = useCallback((vid: string) => {
    const addedKeys = expansionEdgeKeysRef.current.get(vid)
    expansionEdgeKeysRef.current.delete(vid)
    setState((prev) => {
      const edges = new Map(prev.edges)
      if (addedKeys) {
        for (const key of addedKeys) edges.delete(key)
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
    expansionEdgeKeysRef.current = new Map()
    setState(EMPTY_STATE)
  }, [])

  return { ...state, setOverview, mergeExpansion, collapse, addNode, reset }
}
