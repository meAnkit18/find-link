import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { EntityGraphNode, EntitySearchHit, GraphNode, RiskResult } from '../api/types'
import JsonView from '../components/common/JsonView'
import InfoTooltip from '../components/common/InfoTooltip'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphCanvas3D from '../components/explorer/GraphCanvas3D'
import GraphControls from '../components/explorer/GraphControls'
import { roleForNode } from '../components/explorer/graphStyle'
import { computeVisibleGraph } from '../components/explorer/graphVisibility'
import { useGraphCanvasState } from '../hooks/useGraphCanvasState'

// Fixed to the canonical schema (packages/ingestion-core/src/ingestion_core/canonical.py):
// person/company/organization are the hub entities everything else attaches to.
const MAIN_TAGS = new Set(['person', 'company', 'organization'])

export function riskColor(level: string): string {
  switch (level) {
    case 'high':
      return '#c23b32'
    case 'medium':
      return '#b5720a'
    default:
      return '#1e8a5f'
  }
}

function toGraphNode(n: EntityGraphNode): GraphNode {
  const properties: Record<string, unknown> = {}
  for (const props of Object.values(n.tags)) Object.assign(properties, props)
  return { vid: n.id, tags: Object.keys(n.tags), label: n.label || n.id, properties }
}

/** Investigation canvas: search people, load their neighborhood into the
 * shared graph canvas, inspect nodes, see risk scores, expand deeper by
 * clicking a node (click again to collapse it), and run shortest-path
 * between two picked nodes. */
export function InvestigationGraphPage() {
  const graphState = useGraphCanvasState()
  const [view, setView] = useState<'2d' | '3d'>('2d')
  const canvas2DRef = useRef<GraphCanvasHandle>(null)
  const canvas3DRef = useRef<GraphCanvasHandle>(null)

  function activeCanvas(): GraphCanvasHandle | null {
    return view === '2d' ? canvas2DRef.current : canvas3DRef.current
  }

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<EntitySearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [selectedVid, setSelectedVid] = useState<string | null>(null)
  const [expandedVids, setExpandedVids] = useState<Set<string>>(new Set())
  const [expandingVids, setExpandingVids] = useState<Set<string>>(new Set())
  const [revealedVids, setRevealedVids] = useState<Set<string>>(new Set())
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [depth, setDepth] = useState(1)
  const [pathSource, setPathSource] = useState<string | null>(null)
  const [pathResult, setPathResult] = useState<unknown>(null)
  const [status, setStatus] = useState<string | null>(null)

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setSearchError(null)
    try {
      const results = await api.searchEntities(searchQuery.trim())
      setSearchResults(results)
      if (results.length === 0) setSearchError('No matches.')
    } catch (err) {
      setSearchResults([])
      setSearchError((err as Error).message)
    }
  }

  async function loadEntity(entityId: string, replace: boolean) {
    if (expandingVids.has(entityId)) return
    setExpandingVids((prev) => new Set(prev).add(entityId))
    setStatus(`Expanding ${entityId} (depth ${depth})…`)
    try {
      const data = await api.expandEntityGraph(entityId, depth)
      const nodes = data.nodes.map(toGraphNode)
      if (replace) {
        const rootNode = nodes.find((n) => n.vid === entityId) ?? {
          vid: entityId,
          tags: [],
          label: entityId,
          properties: {},
        }
        graphState.setOverview([rootNode], [])
        graphState.mergeExpansion(entityId, nodes, data.edges)
        setExpandedVids(new Set([entityId]))
      } else {
        graphState.mergeExpansion(entityId, nodes, data.edges)
        setExpandedVids((prev) => new Set(prev).add(entityId))
      }
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    } finally {
      setExpandingVids((prev) => {
        const next = new Set(prev)
        next.delete(entityId)
        return next
      })
    }
  }

  function nodeRole(vid: string): 'main' | 'sub' {
    const node = graphState.nodes.get(vid)
    if (!node) return 'sub'
    return roleForNode(node, MAIN_TAGS)
  }

  /** Reveal (or hide) a main node's own already-loaded sub-nodes — a pure,
   * instant visibility toggle, decoupled from network fetching. The first
   * time a main node is revealed, if we've never fetched its neighborhood
   * (true for any main node discovered only as someone else's neighbor),
   * also fetch it so there's something to reveal. Hiding never discards
   * fetched data — re-revealing is instant, no spinner. Sub nodes have no
   * expand affordance; clicking one is select-only. */
  function toggleReveal(vid: string) {
    if (nodeRole(vid) !== 'main') return
    const alreadyRevealed = revealedVids.has(vid)
    setRevealedVids((prev) => {
      const next = new Set(prev)
      if (alreadyRevealed) next.delete(vid)
      else next.add(vid)
      return next
    })
    if (!alreadyRevealed && !expandedVids.has(vid)) {
      void loadEntity(vid, false)
    }
  }

  async function handleSelectResult(hit: EntitySearchHit) {
    setSearchResults([])
    setSearchQuery('')
    setSelectedVid(hit.entity_id)
    await loadEntity(hit.entity_id, true)
  }

  async function fetchRisk(entityId: string) {
    setRisk(null)
    try {
      setRisk(await api.getEntityRisk(entityId))
    } catch (err) {
      setStatus(`✗ risk: ${(err as Error).message}`)
    }
  }

  async function runShortestPath(targetId: string) {
    if (!pathSource) return
    setStatus(`Path ${pathSource} → ${targetId}…`)
    try {
      setPathResult(await api.shortestPath(pathSource, targetId))
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    } finally {
      setPathSource(null)
    }
  }

  const selectedNode = selectedVid ? graphState.nodes.get(selectedVid) ?? null : null
  const { visibleNodes: canvasNodes, visibleEdges: canvasEdges } = useMemo(
    () =>
      computeVisibleGraph(
        Array.from(graphState.nodes.values()),
        Array.from(graphState.edges.values()),
        MAIN_TAGS,
        revealedVids,
      ),
    [graphState.nodes, graphState.edges, revealedVids],
  )

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto' }}>
          <strong>Investigation</strong>
        </div>
        <div className="explorer-topbar__search" style={{ position: 'relative' }}>
          <div className="row">
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="Search people, companies, and more…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button className="btn btn--primary" onClick={handleSearch}>
              Search
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="card search-dropdown">
              {searchResults.map((hit) => (
                <button
                  key={hit.entity_id}
                  className="list-item"
                  onClick={() => handleSelectResult(hit)}
                >
                  <strong>{hit.label || hit.entity_id}</strong>
                  <div className="mono muted">
                    {hit.entity_type} · {hit.entity_id}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="muted">Depth</span>
          <InfoTooltip text="How many steps out from a person or company to load onto the graph at once." />
          <select className="select" style={{ width: 90 }} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
            <option value={3}>3 hops</option>
          </select>
        </label>
      </div>

      {(status || searchError) && (
        <div className="status-strip">{status ?? searchError}</div>
      )}

      <div className="explorer-body">
        <div className="explorer-center">
          {view === '2d' ? (
            <GraphCanvas
              ref={canvas2DRef}
              nodes={canvasNodes}
              edges={canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={toggleReveal}
              onZoomChange={setZoom}
            />
          ) : (
            <GraphCanvas3D
              ref={canvas3DRef}
              nodes={canvasNodes}
              edges={canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={toggleReveal}
            />
          )}
          <GraphControls
            view={view}
            onToggleView={() => setView((v) => (v === '2d' ? '3d' : '2d'))}
            onZoomIn={() => activeCanvas()?.zoomIn()}
            onZoomOut={() => activeCanvas()?.zoomOut()}
            onFit={() => activeCanvas()?.fit()}
            onCenterSelected={() => activeCanvas()?.centerSelected()}
            onRelayout={() => activeCanvas()?.relayout()}
            onExportPng={() => activeCanvas()?.exportPng()}
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
        </div>

        <div className="explorer-right">
          {selectedNode ? (
            <div className="panel stack">
              <h3>{selectedNode.label}</h3>
              <p className="text-secondary mono">{selectedNode.vid}</p>

              <div className="row" style={{ flexWrap: 'wrap' }}>
                {nodeRole(selectedNode.vid) === 'main' && (
                  <>
                    <button
                      className="btn btn--primary"
                      onClick={() => toggleReveal(selectedNode.vid)}
                      disabled={expandingVids.has(selectedNode.vid)}
                    >
                      {expandingVids.has(selectedNode.vid)
                        ? 'Loading…'
                        : revealedVids.has(selectedNode.vid)
                          ? 'Hide details'
                          : 'Show details'}
                    </button>
                    <InfoTooltip text="Reveal or hide this person's or company's own attribute nodes (phone, email, address, ...) on the canvas." />
                  </>
                )}
                <button className="btn" onClick={() => fetchRisk(selectedNode.vid)}>
                  Risk
                </button>
                <InfoTooltip text="Calculate a risk score for this person or company based on their connections and known flags." />
                {pathSource && pathSource !== selectedNode.vid ? (
                  <button className="btn" onClick={() => runShortestPath(selectedNode.vid)}>
                    Path from {pathSource.slice(0, 12)}… → here
                  </button>
                ) : (
                  <button className="btn" onClick={() => setPathSource(selectedNode.vid)}>
                    Path: set as source
                  </button>
                )}
                <InfoTooltip text="Find the shortest chain of connections between two people or companies. Pick a starting point here, then click another node to find the path to it." />
              </div>

              {risk && risk.entity_id === selectedNode.vid && (
                <div className="risk-section">
                  <h4>Risk assessment</h4>
                  <div className="risk-badge" style={{ background: riskColor(risk.level), color: '#fff' }}>
                    {risk.level.toUpperCase()} · {risk.score.toFixed(2)}
                  </div>
                  {risk.factors.length > 0 && (
                    <ul className="risk-factors">
                      {risk.factors.map((f, i) => (
                        <li key={i}>{f.explanation}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <h4>Properties</h4>
              <JsonView data={selectedNode.properties} title="properties" initiallyOpen />
            </div>
          ) : (
            <div className="panel">
              <h3>Investigation tools</h3>
              <p className="text-secondary">
                Search a person, company, or anything else, then click a result to load its
                connections onto the canvas — the "Depth" selector controls how many hops
                out. People, companies, and organizations render larger; related details
                like phone numbers or addresses render smaller. Click an expanded node
                again to collapse it back.
              </p>
            </div>
          )}

          {pathResult !== null && (
            <div className="panel">
              <JsonView data={pathResult} title="shortest-path result" />
              <button className="btn" onClick={() => setPathResult(null)}>
                Clear
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
