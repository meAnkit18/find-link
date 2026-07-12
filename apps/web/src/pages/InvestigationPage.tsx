import { useCallback, useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { api } from '../api/client'
import type { EntityGraph, EntityGraphNode, EntitySearchHit, RiskResult } from '../api/types'
import GraphPicker from '../components/common/GraphPicker'
import JsonView from '../components/common/JsonView'

cytoscape.use(fcose)

export function riskColor(level: string): string {
  switch (level) {
    case 'high':
      return '#DC2626'
    case 'medium':
      return '#F59E0B'
    default:
      return '#10B981'
  }
}

/** Investigation canvas: search people, load their neighborhood into a
 * Cytoscape canvas, inspect nodes, see risk scores, expand deeper, and run
 * shortest-path between two picked nodes. */
export function InvestigationGraphPage() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  const [graphId, setGraphId] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [entityType, setEntityType] = useState('person')
  const [searchResults, setSearchResults] = useState<EntitySearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [selectedNode, setSelectedNode] = useState<EntityGraphNode | null>(null)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [depth, setDepth] = useState(1)
  const [pathSource, setPathSource] = useState<string | null>(null)
  const [pathResult, setPathResult] = useState<unknown>(null)
  const [status, setStatus] = useState<string | null>(null)

  const nodesRef = useRef<Map<string, EntityGraphNode>>(new Map())

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': '#3B82F6',
            color: '#E5E7EB',
            'text-wrap': 'wrap',
            'text-max-width': '120px',
            'font-size': 10,
            width: 40,
            height: 40,
          },
        },
        {
          selector: 'node:selected',
          style: { 'border-width': 3, 'border-color': '#F59E0B' },
        },
        {
          selector: 'edge',
          style: {
            width: 2,
            label: 'data(label)',
            'curve-style': 'bezier',
            'line-color': '#475569',
            'target-arrow-color': '#475569',
            'target-arrow-shape': 'triangle',
            'font-size': 8,
            color: '#94A3B8',
          },
        },
      ],
    })
    cyRef.current = cy

    cy.on('tap', 'node', (evt) => {
      const id = evt.target.id() as string
      const node = nodesRef.current.get(id) ?? { id, label: id, tags: {} }
      setSelectedNode(node)
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) setSelectedNode(null)
    })

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  const mergeGraph = useCallback((data: EntityGraph, replace: boolean) => {
    const cy = cyRef.current
    if (!cy) return
    if (replace) {
      cy.elements().remove()
      nodesRef.current = new Map()
    }
    for (const node of data.nodes) {
      nodesRef.current.set(node.id, node)
      if (cy.getElementById(node.id).length === 0) {
        cy.add({ group: 'nodes', data: { id: node.id, label: node.label || node.id } })
      }
    }
    for (const edge of data.edges) {
      const edgeId = `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
      if (
        cy.getElementById(edgeId).length === 0 &&
        cy.getElementById(edge.src).length > 0 &&
        cy.getElementById(edge.dst).length > 0
      ) {
        cy.add({
          group: 'edges',
          data: { id: edgeId, source: edge.src, target: edge.dst, label: edge.edge_type },
        })
      }
    }
    cy.layout({ name: 'fcose' }).run()
  }, [])

  async function handleSearch() {
    if (!graphId || !searchQuery.trim()) return
    setSearchError(null)
    try {
      const results = await api.searchEntities(graphId, searchQuery.trim(), entityType.trim() || 'person')
      setSearchResults(results)
      if (results.length === 0) setSearchError('No matches.')
    } catch (err) {
      setSearchResults([])
      setSearchError((err as Error).message)
    }
  }

  async function loadEntity(entityId: string, replace: boolean) {
    if (!graphId) return
    setStatus(`Expanding ${entityId} (depth ${depth})…`)
    try {
      const data = await api.expandEntityGraph(graphId, entityId, depth)
      mergeGraph(data, replace)
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    }
  }

  async function handleSelectResult(hit: EntitySearchHit) {
    setSearchResults([])
    setSearchQuery('')
    await loadEntity(hit.entity_id, true)
  }

  async function fetchRisk(entityId: string) {
    setRisk(null)
    try {
      setRisk(await api.getEntityRisk(graphId, entityId))
    } catch (err) {
      setStatus(`✗ risk: ${(err as Error).message}`)
    }
  }

  async function runShortestPath(targetId: string) {
    if (!pathSource || !graphId) return
    setStatus(`Path ${pathSource} → ${targetId}…`)
    try {
      setPathResult(await api.shortestPath(graphId, pathSource, targetId))
      setStatus(null)
    } catch (err) {
      setStatus(`✗ ${(err as Error).message}`)
    } finally {
      setPathSource(null)
    }
  }

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto' }}>
          <strong>Investigation</strong>
          <div style={{ width: 220 }}>
            <GraphPicker value={graphId} onChange={setGraphId} label="" />
          </div>
        </div>
        <div className="explorer-topbar__search" style={{ position: 'relative' }}>
          <div className="row">
            <input
              className="input"
              style={{ width: 110 }}
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              title="Entity type (tag)"
            />
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder={graphId ? 'Search entities by name…' : 'Pick a graph first'}
              disabled={!graphId}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button className="btn btn--primary" disabled={!graphId} onClick={handleSearch}>
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
                  <div className="mono muted">{hit.entity_id}</div>
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="row" style={{ gap: 'var(--space-2)' }}>
          <span className="muted">Depth</span>
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
        <div className="explorer-center" ref={containerRef} />

        <div className="explorer-right">
          {selectedNode ? (
            <div className="panel stack">
              <h3>{selectedNode.label || selectedNode.id}</h3>
              <p className="text-secondary mono">{selectedNode.id}</p>

              <div className="row" style={{ flexWrap: 'wrap' }}>
                <button className="btn btn--primary" onClick={() => loadEntity(selectedNode.id, false)}>
                  Expand
                </button>
                <button className="btn" onClick={() => fetchRisk(selectedNode.id)}>
                  Risk
                </button>
                {pathSource && pathSource !== selectedNode.id ? (
                  <button className="btn" onClick={() => runShortestPath(selectedNode.id)}>
                    Path from {pathSource.slice(0, 12)}… → here
                  </button>
                ) : (
                  <button className="btn" onClick={() => setPathSource(selectedNode.id)}>
                    Path: set as source
                  </button>
                )}
              </div>

              {risk && risk.entity_id === selectedNode.id && (
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

              <h4>Tags / properties</h4>
              <JsonView data={selectedNode.tags} title="tags" initiallyOpen />
            </div>
          ) : (
            <div className="panel">
              <h3>Investigation tools</h3>
              <p className="text-secondary">
                Pick a graph, search an entity, then click nodes on the canvas
                to inspect, expand, score risk, or run a shortest path.
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
