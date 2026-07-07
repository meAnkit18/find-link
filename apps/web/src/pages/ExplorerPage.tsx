import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { GraphEdge, GraphNode, SearchResult } from '../api/types'
import { useExplorerStore } from '../store/explorerStore'
import GraphCanvas from '../components/explorer/GraphCanvas'
import SearchBar from '../components/explorer/SearchBar'
import FilterPanel from '../components/explorer/FilterPanel'
import NodeDetailPanel from '../components/explorer/NodeDetailPanel'

function edgeKey(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

interface GraphData {
  nodes: Map<string, GraphNode>
  edges: Map<string, GraphEdge>
}

export default function ExplorerPage() {
  const { graphId } = useParams<{ graphId: string }>()
  const rootVidsRef = useRef<Set<string>>(new Set())
  const [graphData, setGraphData] = useState<GraphData>({ nodes: new Map(), edges: new Map() })

  const {
    selectedVid,
    expandedVids,
    hiddenTags,
    hiddenEdgeTypes,
    select,
    markExpanded,
    markCollapsed,
    toggleTag,
    toggleEdgeType,
    reset,
  } = useExplorerStore()

  const graphQuery = useQuery({ queryKey: ['graph', graphId], queryFn: () => api.getGraph(graphId!) })
  const schemaQuery = useQuery({ queryKey: ['schema', graphId], queryFn: () => api.getSchema(graphId!) })
  const overviewQuery = useQuery({
    queryKey: ['overview', graphId],
    queryFn: () => api.getOverview(graphId!, 40),
  })

  // Reset canvas + selection state when navigating to a different graph.
  useEffect(() => {
    reset()
    rootVidsRef.current = new Set()
    setGraphData({ nodes: new Map(), edges: new Map() })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId])

  useEffect(() => {
    if (!overviewQuery.data) return
    rootVidsRef.current = new Set(overviewQuery.data.nodes.map((n) => n.vid))
    setGraphData({
      nodes: new Map(overviewQuery.data.nodes.map((n) => [n.vid, n])),
      edges: new Map(overviewQuery.data.edges.map((e) => [edgeKey(e), e])),
    })
  }, [overviewQuery.data])

  async function expandNode(vid: string) {
    const edgeTypes = schemaQuery.data?.edge_types ?? []
    const nextNodes: GraphNode[] = []
    const nextEdges: GraphEdge[] = []

    await Promise.all(
      edgeTypes.map(async (edgeType) => {
        const [outNeighbors, inNeighbors] = await Promise.all([
          api.getNeighbors(graphId!, vid, { edgeType, direction: 'out', limit: 100 }),
          api.getNeighbors(graphId!, vid, { edgeType, direction: 'in', limit: 100 }),
        ])
        for (const n of outNeighbors) {
          nextNodes.push(n)
          nextEdges.push({ src: vid, dst: n.vid, edge_type: edgeType, rank: 0, properties: {} })
        }
        for (const n of inNeighbors) {
          nextNodes.push(n)
          nextEdges.push({ src: n.vid, dst: vid, edge_type: edgeType, rank: 0, properties: {} })
        }
      }),
    )

    setGraphData((prev) => {
      const nodes = new Map(prev.nodes)
      nextNodes.forEach((n) => nodes.set(n.vid, n))
      const edges = new Map(prev.edges)
      nextEdges.forEach((e) => edges.set(edgeKey(e), e))
      return { nodes, edges }
    })
    markExpanded(vid)
  }

  function collapseNode(vid: string) {
    setGraphData((prev) => {
      const edges = new Map(prev.edges)
      for (const [key, edge] of prev.edges) {
        if (edge.src === vid || edge.dst === vid) edges.delete(key)
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
    markCollapsed(vid)
  }

  async function handleSearchResult(result: SearchResult) {
    if (!graphData.nodes.has(result.vid)) {
      const node = await api.getNode(graphId!, result.vid)
      setGraphData((prev) => ({
        nodes: new Map(prev.nodes).set(node.vid, node),
        edges: prev.edges,
      }))
    }
    select(result.vid)
  }

  const visibleNodes = useMemo(
    () => Array.from(graphData.nodes.values()).filter((n) => !n.tags.some((t) => hiddenTags.has(t))),
    [graphData.nodes, hiddenTags],
  )
  const visibleVids = useMemo(() => new Set(visibleNodes.map((n) => n.vid)), [visibleNodes])
  const visibleEdges = useMemo(
    () =>
      Array.from(graphData.edges.values()).filter(
        (e) => !hiddenEdgeTypes.has(e.edge_type) && visibleVids.has(e.src) && visibleVids.has(e.dst),
      ),
    [graphData.edges, hiddenEdgeTypes, visibleVids],
  )

  if (graphQuery.isError) {
    return (
      <main className="page">
        <p style={{ color: 'var(--color-danger)' }}>This graph could not be found.</p>
        <Link to="/">← All graphs</Link>
      </main>
    )
  }

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row">
          <Link to="/">← All graphs</Link>
          <strong>{graphQuery.data?.name}</strong>
        </div>
        <div className="explorer-topbar__search">
          {graphId && <SearchBar graphId={graphId} onResultClick={handleSearchResult} />}
        </div>
        <Link className="btn" to={`/graphs/${graphId}/upload`}>
          Import more data
        </Link>
      </div>

      <div className="explorer-layout">
        {schemaQuery.data && (
          <div className="explorer-filter-panel">
            <FilterPanel
              schema={schemaQuery.data}
              hiddenTags={hiddenTags}
              hiddenEdgeTypes={hiddenEdgeTypes}
              onToggleTag={toggleTag}
              onToggleEdgeType={toggleEdgeType}
            />
          </div>
        )}

        <div className="card explorer-canvas">
          {overviewQuery.isLoading && (
            <div className="row" style={{ height: '100%', justifyContent: 'center' }}>
              <span className="spinner" /> Loading graph…
            </div>
          )}
          {overviewQuery.data && visibleNodes.length === 0 && (
            <div className="row" style={{ height: '100%', justifyContent: 'center' }}>
              <p className="muted">This graph is empty — import a CSV to get started.</p>
            </div>
          )}
          {graphId && (
            <GraphCanvas
              nodes={visibleNodes}
              edges={visibleEdges}
              selectedVid={selectedVid}
              onSelect={select}
              onExpand={expandNode}
            />
          )}
        </div>

        {graphId && selectedVid && (
          <div className="explorer-detail-panel">
            <NodeDetailPanel
              graphId={graphId}
              vid={selectedVid}
              isExpanded={expandedVids.has(selectedVid)}
              onExpand={() => expandNode(selectedVid)}
              onCollapse={() => collapseNode(selectedVid)}
              onClose={() => select(null)}
            />
          </div>
        )}
      </div>
    </main>
  )
}
