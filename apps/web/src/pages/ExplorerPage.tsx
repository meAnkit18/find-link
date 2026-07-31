import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { SearchResult } from '../api/types'
import { useExplorerStore } from '../store/explorerStore'
import { useGraphCanvasState } from '../hooks/useGraphCanvasState'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphControls from '../components/explorer/GraphControls'
import SearchBar from '../components/explorer/SearchBar'
import FilterPanel from '../components/explorer/FilterPanel'
import NodeDetailPanel from '../components/explorer/NodeDetailPanel'

export default function ExplorerPage() {
  const { graphId } = useParams<{ graphId: string }>()
  const graphState = useGraphCanvasState()
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
    mainTags,
    select,
    markExpanded,
    markCollapsed,
    toggleTag,
    toggleEdgeType,
    toggleMainTag,
    reset,
  } = useExplorerStore()

  const graphQuery = useQuery({ queryKey: ['graph', graphId], queryFn: () => api.getGraph(graphId!) })
  const schemaQuery = useQuery({ queryKey: ['schema', graphId], queryFn: () => api.getSchema(graphId!) })
  const mainTagsKey = useMemo(() => Array.from(mainTags).sort().join(','), [mainTags])
  const overviewQuery = useQuery({
    queryKey: ['overview', graphId, mainTagsKey],
    queryFn: () => api.getOverview(graphId!, 40, mainTags.size > 0 ? Array.from(mainTags) : undefined),
  })

  // Reset canvas + selection state when navigating to a different graph.
  useEffect(() => {
    reset()
    graphState.reset()
    setExpandingVids(new Set())
    setActionError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphId])

  useEffect(() => {
    if (!overviewQuery.data) return
    graphState.setOverview(overviewQuery.data.nodes, overviewQuery.data.edges)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overviewQuery.data])

  async function expandNode(vid: string) {
    if (expandingVids.has(vid)) return // an expansion for this node is already in flight
    setExpandingVids((prev) => new Set(prev).add(vid))
    setActionError(null)

    try {
      const subgraph = await api.getNeighborsWithEdges(graphId!, vid, { direction: 'both', limit: 200 })
      graphState.mergeExpansion(vid, subgraph.nodes, subgraph.edges)
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
    graphState.collapse(vid)
    markCollapsed(vid)
  }

  function toggleExpand(vid: string) {
    if (expandedVids.has(vid)) collapseNode(vid)
    else void expandNode(vid)
  }

  async function handleSearchResult(result: SearchResult) {
    try {
      if (!graphState.nodes.has(result.vid)) {
        const node = await api.getNode(graphId!, result.vid)
        graphState.addNode(node)
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
    () => Array.from(graphState.nodes.values()).filter((n) => !n.tags.some((t) => hiddenTags.has(t))),
    [graphState.nodes, hiddenTags],
  )
  const visibleVids = useMemo(() => new Set(visibleNodes.map((n) => n.vid)), [visibleNodes])
  const visibleEdges = useMemo(
    () =>
      Array.from(graphState.edges.values()).filter(
        (e) => !hiddenEdgeTypes.has(e.edge_type) && visibleVids.has(e.src) && visibleVids.has(e.dst),
      ),
    [graphState.edges, hiddenEdgeTypes, visibleVids],
  )

  const graphIsEmpty = overviewQuery.data != null && graphState.nodes.size === 0
  const allFilteredOut = graphState.nodes.size > 0 && visibleNodes.length === 0

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
              mainTags={mainTags}
              onToggleTag={toggleTag}
              onToggleEdgeType={toggleEdgeType}
              onToggleMainTag={toggleMainTag}
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
                  mainTags={mainTags}
                  onSelect={select}
                  onToggleExpand={toggleExpand}
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
              onExpand={() => void expandNode(selectedVid)}
              onCollapse={() => collapseNode(selectedVid)}
              onClose={() => select(null)}
            />
          </div>
        )}
      </div>
    </main>
  )
}
