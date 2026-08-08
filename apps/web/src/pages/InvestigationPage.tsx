import { useCallback, useMemo, useRef, useState } from 'react'
import type { Position } from 'cytoscape'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import type { EntitySearchHit, PersonLink, PersonLinkVia, RiskResult } from '../api/types'
import JsonView from '../components/common/JsonView'
import PropertiesList from '../components/common/PropertiesList'
import InfoTooltip from '../components/common/InfoTooltip'
import { humanizeLabel } from '../components/common/format'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphCanvas3D from '../components/explorer/GraphCanvas3D'
import GraphControls from '../components/explorer/GraphControls'
import { colorForTag } from '../components/explorer/graphStyle'
import { computeRadialPositions, type RadialChild } from '../components/explorer/radialLayout'
import { usePersonNetworkState, PERSON_TAG } from '../hooks/usePersonNetworkState'
import { useResizablePanel } from '../hooks/useResizablePanel'

// People are the only primary nodes here: everything else on the canvas is
// an attribute fanned out from a person the investigator clicked.
const MAIN_TAGS = new Set([PERSON_TAG])

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

function viaText(via: PersonLinkVia): string {
  // Only a shared_attribute is something the two people have in common; the
  // other kinds carry a ready sentence, and rendering them as "company: X"
  // would claim they share X when they don't.
  if (via.kind === 'shared_attribute') {
    return `${via.connector_tag.replace(/_/g, ' ')}: ${via.connector_label}`
  }
  return via.label
}

/** Investigation canvas: search a person, see who they're connected to
 * within 1/2/3 degrees and *why* (the shared phone, address, employer, ...),
 * click any person to fan their own details out in a ring around them, and
 * run shortest-path between two picked people. */
export function InvestigationGraphPage() {
  const graph = usePersonNetworkState()
  const [view, setView] = useState<'2d' | '3d'>('2d')
  const canvas2DRef = useRef<GraphCanvasHandle>(null)
  const canvas3DRef = useRef<GraphCanvasHandle>(null)

  function activeCanvas(): GraphCanvasHandle | null {
    return view === '2d' ? canvas2DRef.current : canvas3DRef.current
  }

  const detailPanel = useResizablePanel({
    defaultWidth: 340,
    min: 280,
    max: 620,
    storageKey: 'investigation.detailPanelWidth',
    side: 'right',
  })

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<EntitySearchHit[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [rootId, setRootId] = useState<string | null>(null)
  const [selectedVid, setSelectedVid] = useState<string | null>(null)
  const [degree, setDegree] = useState(1)
  const [minConfidence, setMinConfidence] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [pathSource, setPathSource] = useState<string | null>(null)
  const [pathResult, setPathResult] = useState<unknown>(null)
  const [status, setStatus] = useState<string | null>(null)

  // Where the force layout put each person. Attribute rings are placed
  // relative to these, so they have to come back from the canvas.
  const [positions, setPositions] = useState<Map<string, Position>>(new Map())
  // A user-dragged attribute's offset from its computed ring slot. Stored as
  // an offset (not an absolute position) so a manually-nudged attribute
  // still tracks its parent if the parent is dragged afterwards — only the
  // "where on the ring" part is overridden.
  const [manualOffsets, setManualOffsets] = useState<Map<string, Position>>(new Map())

  const handlePositionsSettled = useCallback((settled: Map<string, Position>) => {
    setPositions(new Map(settled))
  }, [])

  const handleParentMoved = useCallback((vid: string, position: Position) => {
    setPositions((prev) => new Map(prev).set(vid, { ...position }))
  }, [])

  const radialChildren = useMemo<RadialChild[]>(
    () =>
      [...graph.attributeParents.entries()].map(([attributeId, parentIds]) => {
        const attribute = graph.attributes.get(parentIds[0])?.find((a) => a.id === attributeId)
        return {
          id: attributeId,
          parentIds,
          sortKey: `${attribute?.tag ?? ''}:${attribute?.label ?? attributeId}`,
        }
      }),
    [graph.attributeParents, graph.attributes],
  )

  const radialBase = useMemo(() => {
    // Every person is an obstacle: a ring must not grow so wide that it
    // swallows the neighbour it sits next to.
    const obstacles = [...graph.personsById.keys()]
      .map((id) => positions.get(id))
      .filter((p): p is Position => p != null)
    return computeRadialPositions(positions, radialChildren, { obstacles })
  }, [positions, radialChildren, graph.personsById])

  const pinnedPositions = useMemo(() => {
    if (manualOffsets.size === 0) return radialBase
    const withOffsets = new Map(radialBase)
    for (const [id, offset] of manualOffsets) {
      const base = radialBase.get(id)
      if (!base) continue
      withOffsets.set(id, { x: base.x + offset.x, y: base.y + offset.y })
    }
    return withOffsets
  }, [radialBase, manualOffsets])

  const handleChildMoved = useCallback(
    (vid: string, position: Position) => {
      const base = radialBase.get(vid)
      if (!base) return
      setManualOffsets((prev) => new Map(prev).set(vid, { x: position.x - base.x, y: position.y - base.y }))
    },
    [radialBase],
  )

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setSearchError(null)
    try {
      // People only: this canvas has no other kind of primary node.
      const results = await api.searchEntities(searchQuery.trim(), PERSON_TAG)
      setSearchResults(results)
      if (results.length === 0) setSearchError('No people matched.')
    } catch (err) {
      setSearchResults([])
      setSearchError((err as Error).message)
    }
  }

  async function loadNetwork(
    personId: string,
    nextDegree: number,
    opts?: { preserveExpanded?: boolean },
  ) {
    setStatus(`Finding connections within ${nextDegree} degree${nextDegree === 1 ? '' : 's'}…`)
    const result = await graph.loadNetwork(personId, nextDegree, {
      minConfidence,
      preserveExpanded: opts?.preserveExpanded,
    })
    // Widening the same question keeps the layout the user is reading; only
    // a new root starts the canvas over.
    if (!opts?.preserveExpanded) {
      setPositions(new Map())
      setManualOffsets(new Map())
    }
    setStatus(
      result
        ? `${result.persons.length - 1} connected ${
            result.persons.length === 2 ? 'person' : 'people'
          } within ${nextDegree} degree${nextDegree === 1 ? '' : 's'}.`
        : null,
    )
  }

  async function handleSelectResult(hit: EntitySearchHit) {
    setSearchResults([])
    setSearchQuery('')
    setRootId(hit.entity_id)
    setSelectedVid(hit.entity_id)
    await loadNetwork(hit.entity_id, degree)
  }

  async function handleDegreeChange(next: number) {
    setDegree(next)
    if (rootId) await loadNetwork(rootId, next, { preserveExpanded: true })
  }

  function isPerson(vid: string): boolean {
    return graph.personsById.has(vid)
  }

  /** A click on a person fans their details out (or folds them back in);
   * a click on an attribute only selects it — attributes have no children. */
  function handleToggle(vid: string) {
    if (!isPerson(vid)) return
    void graph.toggleExpand(vid)
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

  const selectedPerson = selectedVid ? graph.personsById.get(selectedVid) ?? null : null
  const selectedAttribute = useMemo(() => {
    if (!selectedVid || selectedPerson) return null
    for (const list of graph.attributes.values()) {
      const found = list.find((a) => a.id === selectedVid)
      if (found) return found
    }
    return null
  }, [selectedVid, selectedPerson, graph.attributes])

  const selectedLinks: PersonLink[] = selectedVid
    ? graph.linksByPerson.get(selectedVid) ?? []
    : []

  // Nothing selected — the right panel falls back to an at-a-glance
  // overview of everyone currently on the canvas, so there's still
  // somewhere to see it all at once instead of having to click through
  // each node individually.
  const allPeople = useMemo(
    () =>
      [...graph.personsById.values()].sort((a, b) => a.degree - b.degree || a.label.localeCompare(b.label)),
    [graph.personsById],
  )
  const attributesByTag = useMemo(() => {
    const byTag = new Map<string, typeof graph.canvasNodes>()
    for (const node of graph.canvasNodes) {
      if (graph.personsById.has(node.vid)) continue // people are listed separately, above
      const tag = node.tags[0] ?? 'attribute'
      const list = byTag.get(tag)
      if (list) list.push(node)
      else byTag.set(tag, [node])
    }
    return [...byTag.entries()].sort((a, b) => b[1].length - a[1].length)
  }, [graph.canvasNodes, graph.personsById])

  const notice = useMemo(() => {
    const parts: string[] = []
    if (graph.network?.truncated) {
      parts.push('Too many connections to show them all — narrow the degree.')
    }
    for (const hub of graph.network?.suppressed_hubs ?? []) {
      parts.push(
        `Skipped ${hub.tag.replace(/_/g, ' ')} "${hub.label}" — shared by ${hub.person_count} people, so it links everyone to everyone.`,
      )
    }
    return parts
  }, [graph.network])

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto' }}>
          <strong>Investigation</strong>
        </div>
        <div className="explorer-topbar__search" style={{ position: 'relative' }}>
          <div className="row" style={{ gap: 'var(--space-1)' }}>
            <div className="search-input-wrap">
              <Search className="search-input-wrap__icon" size={14} />
              <input
                className="input input--search"
                placeholder="Search for a person…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <button className="btn btn--primary btn-sm" onClick={handleSearch}>
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
          <span className="muted">Degree</span>
          <InfoTooltip text="How far apart two people can be. 1 = they share something directly (a phone, an address, an employer). 2 = a friend of a friend. 3 = one step further out." />
          <select
            className="select"
            style={{ width: 110 }}
            value={degree}
            onChange={(e) => handleDegreeChange(Number(e.target.value))}
          >
            <option value={1}>1 degree</option>
            <option value={2}>2 degrees</option>
            <option value={3}>3 degrees</option>
          </select>
        </label>
      </div>

      {(status || searchError || graph.error) && (
        <div className="status-strip">{graph.error ?? searchError ?? status}</div>
      )}
      {notice.map((line) => (
        <div className="status-strip" key={line}>
          {line}
        </div>
      ))}

      <div className="explorer-body">
        <div className="explorer-center">
          {view === '2d' ? (
            <GraphCanvas
              ref={canvas2DRef}
              nodes={graph.canvasNodes}
              edges={graph.canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={handleToggle}
              onZoomChange={setZoom}
              pinnedPositions={pinnedPositions}
              onParentMoved={handleParentMoved}
              onChildMoved={handleChildMoved}
              onPositionsSettled={handlePositionsSettled}
            />
          ) : (
            <GraphCanvas3D
              ref={canvas3DRef}
              nodes={graph.canvasNodes}
              edges={graph.canvasEdges}
              selectedVid={selectedVid}
              mainTags={MAIN_TAGS}
              onSelect={setSelectedVid}
              onToggleExpand={handleToggle}
              ringParents={graph.attributeParents}
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

        {detailPanel.isDesktop && (
          <div
            className="resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize detail panel"
            {...detailPanel.handleProps}
          />
        )}

        <div
          className="explorer-right"
          style={detailPanel.isDesktop ? { width: detailPanel.width } : undefined}
        >
          {selectedPerson ? (
            <div className="panel stack">
              <div>
                <h3 style={{ marginBottom: 4 }}>{selectedPerson.label}</h3>
                <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--space-1)' }}>
                  <span className="tag-chip">
                    <span className="tag-dot" style={{ background: colorForTag(PERSON_TAG) }} />
                    {selectedPerson.entity_type}
                  </span>
                </div>
              </div>
              <p className="text-secondary mono">{selectedPerson.id}</p>
              <p className="text-secondary">
                {selectedPerson.degree === 0
                  ? 'The person you searched for'
                  : `${selectedPerson.degree} degree${selectedPerson.degree === 1 ? '' : 's'} from ${
                      graph.personsById.get(graph.network?.root_id ?? '')?.label ?? 'the subject'
                    }`}
              </p>

              <div className="row" style={{ flexWrap: 'wrap' }}>
                <button
                  className="btn btn--primary"
                  onClick={() => handleToggle(selectedPerson.id)}
                  disabled={graph.loadingAttributes.has(selectedPerson.id)}
                >
                  {graph.loadingAttributes.has(selectedPerson.id)
                    ? 'Loading…'
                    : graph.expanded.has(selectedPerson.id)
                      ? 'Hide details'
                      : 'Show details'}
                </button>
                <InfoTooltip text="Fan this person's own details (phone, email, address, passport, ...) out in a ring around them." />
                <button className="btn" onClick={() => fetchRisk(selectedPerson.id)}>
                  Risk
                </button>
                <InfoTooltip text="Calculate a risk score for this person based on their connections and known flags." />
                {pathSource && pathSource !== selectedPerson.id ? (
                  <button className="btn" onClick={() => runShortestPath(selectedPerson.id)}>
                    Path from {pathSource.slice(0, 12)}… → here
                  </button>
                ) : (
                  <button className="btn" onClick={() => setPathSource(selectedPerson.id)}>
                    Path: set as source
                  </button>
                )}
                <InfoTooltip text="Find the shortest chain of connections between two people. Pick a starting point here, then click another person." />
              </div>

              {selectedLinks.length > 0 && (
                <div className="stack">
                  <h4>Why connected</h4>
                  <ul className="risk-factors">
                    {selectedLinks.map((link) => {
                      const otherId = link.source === selectedPerson.id ? link.target : link.source
                      const other = graph.personsById.get(otherId)
                      return (
                        <li key={`${link.source}|${link.target}`}>
                          <button className="link-button" onClick={() => setSelectedVid(otherId)}>
                            {other?.label ?? otherId}
                          </button>
                          <div className="mono muted">
                            {link.via.map(viaText).join(' · ')}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}

              {risk && risk.entity_id === selectedPerson.id && (
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
              <PropertiesList properties={selectedPerson.properties} />
            </div>
          ) : selectedAttribute ? (
            <div className="panel stack">
              <div>
                <h3 style={{ marginBottom: 4 }}>{selectedAttribute.label}</h3>
                <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--space-1)' }}>
                  <span className="tag-chip">
                    <span className="tag-dot" style={{ background: colorForTag(selectedAttribute.tag) }} />
                    {selectedAttribute.tag.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>
              <p className="text-secondary mono">{selectedAttribute.id}</p>
              {selectedAttribute.shared_with.length > 0 ? (
                <div className="stack">
                  <h4>Shared with</h4>
                  <ul className="risk-factors">
                    {selectedAttribute.shared_with.map((personId) => (
                      <li key={personId}>
                        <button className="link-button" onClick={() => setSelectedVid(personId)}>
                          {graph.personsById.get(personId)?.label ?? personId}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-secondary">Held by this person alone.</p>
              )}
              <h4>Properties</h4>
              <PropertiesList properties={selectedAttribute.properties} />
            </div>
          ) : graph.network ? (
            <div className="panel stack">
              <div>
                <h3 style={{ marginBottom: 4 }}>Everyone on this canvas</h3>
                <p className="text-secondary">
                  Nothing selected — here's everything currently shown. Click a person or
                  a detail below (or on the canvas) to see its full profile.
                </p>
              </div>

              <div className="stack">
                <h4>People ({allPeople.length})</h4>
                <div className="stack" style={{ gap: 4 }}>
                  {allPeople.map((person) => (
                    <button
                      key={person.id}
                      className="list-item"
                      onClick={() => setSelectedVid(person.id)}
                    >
                      <div className="row" style={{ justifyContent: 'space-between', gap: 'var(--space-2)' }}>
                        <strong>{person.label}</strong>
                        <span className="badge">
                          {person.degree === 0 ? 'root' : `${person.degree}°`}
                        </span>
                      </div>
                      <div className="mono muted" style={{ fontSize: 11 }}>
                        {person.entity_type}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {attributesByTag.length > 0 && (
                <div className="stack">
                  <h4>Details shown</h4>
                  <div className="stack">
                    {attributesByTag.map(([tag, tagNodes]) => (
                      <div key={tag}>
                        <span className="tag-chip" style={{ marginBottom: 4 }}>
                          <span className="tag-dot" style={{ background: colorForTag(tag) }} />
                          {humanizeLabel(tag)} ({tagNodes.length})
                        </span>
                        <div className="stack" style={{ gap: 4, marginTop: 4 }}>
                          {tagNodes.map((node) => (
                            <button
                              key={node.vid}
                              className="list-item"
                              onClick={() => setSelectedVid(node.vid)}
                            >
                              {node.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="panel">
              <h3>Investigation tools</h3>
              <p className="text-secondary">
                Search for a person and pick a result. The canvas then shows the other
                people they're connected to — two people are connected when they share
                something (a phone, an email, an address, a passport, an employer) or
                have a direct relationship. "Degree" controls how far that chain runs:
                1 is a direct share, 2 is a friend of a friend, 3 one step further.
              </p>
              <p className="text-secondary">
                Click any person to fan their own details out in a ring around them, and
                click again to fold them back in. Click a link to see exactly what the
                two people have in common.
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
