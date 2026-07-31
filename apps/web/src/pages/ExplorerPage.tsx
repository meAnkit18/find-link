import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { GraphEdge, GraphNode, SearchResult } from '../api/types'
import { useExplorerStore } from '../store/explorerStore'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphControls from '../components/explorer/GraphControls'
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
  // Edge keys each expansion added, so collapse removes only those (and not
  // the original overview edges that happened to touch the same node).
  const expansionEdgeKeysRef = useRef<Map<string, Set<string>>>(new Map())
  const [graphData, setGraphData] = useState<GraphData>({ nodes: new Map(), edges: new Map() })
  const [expandingVids, setExpandingVids] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const canvasRef = useRef<GraphCanvasHandle>(null)

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
    expansionEdgeKeysRef.current = new Map()
    setGraphData({ nodes: new Map(), edges: new Map() })
    setExpandingVids(new Set())
    setActionError(null)
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
    const edgeTypes = schemaQuery.data?.edge_types
    if (!edgeTypes || edgeTypes.length === 0) {
      // Without the schema we would fetch nothing; refusing (instead of
      // silently marking the node expanded) keeps the UI honest.
      setActionError('The graph schema is still loading — try expanding again in a moment.')
      return
    }
    if (expandingVids.has(vid)) return // an expansion for this node is already in flight
    setExpandingVids((prev) => new Set(prev).add(vid))
    setActionError(null)

    try {
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
        nextNodes.forEach((n) => {
          if (!nodes.has(n.vid)) nodes.set(n.vid, n)
        })
        const edges = new Map(prev.edges)
        const addedKeys = expansionEdgeKeysRef.current.get(vid) ?? new Set<string>()
        nextEdges.forEach((e) => {
          const key = edgeKey(e)
          if (!edges.has(key)) addedKeys.add(key)
          edges.set(key, e)
        })
        expansionEdgeKeysRef.current.set(vid, addedKeys)
        return { nodes, edges }
      })
      markExpanded(vid)
    } catch (err) {
      setActionError(
        err instanceof Error ? `Could not expand this node: ${err.message}` : 'Could not expand this node.',
      )
    } finally {
      setExpandingVids((prev) => {
        const next = new Set(prev)
        next.delete(vid)
        return next
      })
    }
  }

  function collapseNode(vid: string) {
    const addedKeys = expansionEdgeKeysRef.current.get(vid)
    expansionEdgeKeysRef.current.delete(vid)
    setGraphData((prev) => {
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
    markCollapsed(vid)
  }

  async function handleSearchResult(result: SearchResult) {
    try {
      if (!graphData.nodes.has(result.vid)) {
        const node = await api.getNode(graphId!, result.vid)
        setGraphData((prev) => ({
          nodes: new Map(prev.nodes).set(node.vid, node),
          edges: prev.edges,
        }))
      }
      select(result.vid)
      setActionError(null)
    } catch {
      setActionError(
        `Could not load "${result.label}" — the search index may be stale. Re-import the data or restart the API to rebuild it.`,
      )
    }
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

  const graphIsEmpty = overviewQuery.data != null && graphData.nodes.size === 0
  const allFilteredOut = graphData.nodes.size > 0 && visibleNodes.length === 0

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
      </div>

      {actionError && <div className="status-strip">{actionError}</div>}

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
          {overviewQuery.isLoading ? (
            <div className="row" style={{ height: '100%', justifyContent: 'center' }}>
              <span className="spinner" /> Loading graph…
            </div>
          ) : overviewQuery.isError ? (
            <div
              className="stack"
              style={{ height: '100%', alignItems: 'center', justifyContent: 'center' }}
            >
              <p className="error-text">
                Could not load the graph overview:{' '}
                {overviewQuery.error instanceof Error ? overviewQuery.error.message : 'unknown error'}
              </p>
              <button className="btn btn-sm" onClick={() => overviewQuery.refetch()}>
                Retry
              </button>
            </div>
          ) : (
            <>
              {graphId && (
                <GraphCanvas
                  ref={canvasRef}
                  key={graphId}
                  nodes={visibleNodes}
                  edges={visibleEdges}
                  selectedVid={selectedVid}
                  onSelect={select}
                  onExpand={expandNode}
                  onZoomChange={setZoom}
                />
              )}
              {graphId && (
                <GraphControls
                  onZoomIn={() => canvasRef.current?.zoomIn()}
                  onZoomOut={() => canvasRef.current?.zoomOut()}
                  onFit={() => canvasRef.current?.fit()}
                  onCenterSelected={() => canvasRef.current?.centerSelected()}
                  onRelayout={() => canvasRef.current?.relayout()}
                  onExportPng={() => canvasRef.current?.exportPng()}
                  onToggleFullscreen={() => {
                    if (!document.fullscreenElement) {
                      document.documentElement.requestFullscreen()
                      setIsFullscreen(true)
                    } else {
                      document.exitFullscreen()
                      setIsFullscreen(false)
                    }
                  }}
                  isFullscreen={isFullscreen}
                  hasSelection={selectedVid != null}
                  zoom={zoom}
                />
              )}
              {graphIsEmpty && (
                <div className="explorer-canvas__overlay">
                  <p className="muted">This graph is empty — import a CSV to get started.</p>
                </div>
              )}
              {allFilteredOut && (
                <div className="explorer-canvas__overlay">
                  <p className="muted">All nodes are hidden by the current filters.</p>
                </div>
              )}
            </>
          )}
        </div>

        {graphId && selectedVid && (
          <div className="explorer-detail-panel">
            <NodeDetailPanel
              graphId={graphId}
              vid={selectedVid}
              isExpanded={expandedVids.has(selectedVid)}
              isExpanding={expandingVids.has(selectedVid)}
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
