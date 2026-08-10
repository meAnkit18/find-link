import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Position } from 'cytoscape'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import type { ConnectionResult, EntitySearchHit, RiskResult } from '../api/types'
import InfoTooltip from '../components/common/InfoTooltip'
import ConnectionChainView from '../components/explorer/connection/ConnectionChainView'
import PersonSearchField from '../components/explorer/connection/PersonSearchField'
import GraphCanvas, { type GraphCanvasHandle } from '../components/explorer/GraphCanvas'
import GraphCanvas3D from '../components/explorer/GraphCanvas3D'
import GraphControls from '../components/explorer/GraphControls'
import DetailPanel from '../components/explorer/detail/DetailPanel'
import { attributeNodeLabel } from '../components/explorer/attributeLabel'
import {
  buildFieldMatchIndex,
  type DetailActions,
  type DetailData,
  type Selection,
} from '../components/explorer/detail/detailModel'
import { computeRadialPositions, type RadialChild } from '../components/explorer/radialLayout'
import { usePersonNetworkState, PERSON_TAG } from '../hooks/usePersonNetworkState'
import { useResizablePanel } from '../hooks/useResizablePanel'

// People are the only primary nodes here: everything else on the canvas is
// an attribute fanned out from a person the investigator clicked.
const MAIN_TAGS = new Set([PERSON_TAG])

/** Investigation canvas: search a person, see who they're connected to
 * within 1/2/3 degrees and *why* (the shared phone, address, employer, ...),
 * and click any person to fan their own details out in a ring around them.
 * A second mode searches two people by name and finds the strongest chain
 * connecting them directly, without exploring first. */
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

  const [mode, setMode] = useState<'explore' | 'connect'>('explore')
  const [personA, setPersonA] = useState<EntitySearchHit | null>(null)
  const [personB, setPersonB] = useState<EntitySearchHit | null>(null)
  const [connectionResult, setConnectionResult] = useState<ConnectionResult | null>(null)
  const [connectionLoading, setConnectionLoading] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)

  const [rootId, setRootId] = useState<string | null>(null)
  // One selection covers all three kinds of subject the panel describes, so
  // opening a relationship necessarily closes whichever node was open and
  // vice versa — two independent states could show a person's profile beside
  // a highlighted arrow that had nothing to do with it.
  const [selection, setSelection] = useState<Selection | null>(null)
  const [degree, setDegree] = useState(1)
  const [minConfidence, setMinConfidence] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [risk, setRisk] = useState<RiskResult | null>(null)
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
    setSelection({ kind: 'person', id: hit.entity_id })
    await loadNetwork(hit.entity_id, degree)
  }

  async function handleFindConnection() {
    if (!personA || !personB) return
    setConnectionLoading(true)
    setConnectionError(null)
    setConnectionResult(null)
    try {
      setConnectionResult(await api.findConnection(personA.entity_id, personB.entity_id))
    } catch (err) {
      setConnectionError((err as Error).message)
    } finally {
      setConnectionLoading(false)
    }
  }

  /** The bridge back to Explore mode from a chain-view person card — reuses
   * the same network load Explore's own search result picker triggers. */
  async function handleExploreFromConnection(personId: string) {
    setMode('explore')
    setRootId(personId)
    setSelection({ kind: 'person', id: personId })
    await loadNetwork(personId, degree)
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

  /** Selecting by vid alone, for the callers that only have one: a canvas
   * click, or a name clicked inside the panel. */
  const openVid = useCallback(
    (vid: string) => {
      setSelection({ kind: graph.personsById.has(vid) ? 'person' : 'attribute', id: vid })
    },
    [graph.personsById],
  )

  /** A click on an arrow. A person-to-person arrow is a projected link and
   * opens as one; a person-to-attribute spoke is not a finding at all, so it
   * resolves to the attribute on its far end — which is what the user was
   * pointing at. */
  const handleSelectEdge = useCallback(
    (source: string, target: string) => {
      const sourceIsPerson = graph.personsById.has(source)
      const targetIsPerson = graph.personsById.has(target)
      if (sourceIsPerson && targetIsPerson) {
        setSelection({ kind: 'link', source, target })
        return
      }
      setSelection({ kind: 'attribute', id: sourceIsPerson ? target : source })
    },
    [graph.personsById],
  )

  const selectedVid = selection && selection.kind !== 'link' ? selection.id : null
  const selectedEdge = useMemo(
    () => (selection?.kind === 'link' ? { source: selection.source, target: selection.target } : null),
    [selection],
  )

  // The panel describes a person by their documents, so those have to be
  // loaded for whoever is selected — including someone reached by clicking a
  // name in the panel, who was never expanded on the canvas. For an attribute
  // it's the holders' records that are needed, which is what lets the panel
  // answer "whose passport is this, and what else do they have".
  //
  // Destructured because the effect depends on these three, not on the whole
  // graph state — every network reload would otherwise re-run it.
  const { attributesById, personsById, ensureAttributes } = graph
  useEffect(() => {
    if (!selection) return
    const wanted =
      selection.kind === 'person'
        ? [selection.id]
        : selection.kind === 'attribute'
          ? attributesById.get(selection.id)?.holders ?? []
          : []
    for (const personId of wanted) {
      // ensureAttributes is a no-op for anything already cached or in
      // flight, so re-running on every cache change settles immediately.
      if (personsById.has(personId)) void ensureAttributes(personId)
    }
  }, [selection, attributesById, personsById, ensureAttributes])

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

  /** Every label the panel can resolve: the people in the projection, plus
   * every attribute fetched so far. A reason can cite a document on the far
   * side of a match whose holder was never opened — those stay unresolved on
   * purpose, and the panel shows the raw id rather than a dead link. */
  const labelFor = useCallback(
    (vid: string) => {
      const person = graph.personsById.get(vid)
      if (person) return person.label
      const entry = graph.attributesById.get(vid)
      return entry ? attributeNodeLabel(entry.attribute) : null
    },
    [graph.personsById, graph.attributesById],
  )

  const detailData = useMemo<DetailData>(
    () => ({
      personsById: graph.personsById,
      links: graph.network?.links ?? [],
      linksByPerson: graph.linksByPerson,
      attributes: graph.attributes,
      attributesById: graph.attributesById,
      expanded: graph.expanded,
      loadingAttributes: graph.loadingAttributes,
      fieldMatches: buildFieldMatchIndex(graph.network?.links ?? []),
      rootLabel: graph.personsById.get(graph.network?.root_id ?? '')?.label ?? 'the subject',
    }),
    [
      graph.personsById,
      graph.network,
      graph.linksByPerson,
      graph.attributes,
      graph.attributesById,
      graph.expanded,
      graph.loadingAttributes,
    ],
  )

  // Rebuilt every render on purpose: these close over state the panel has to
  // see fresh (the expanded set), and the panel isn't memoized, so a stable
  // identity would buy nothing and could only go stale.
  const detailActions: DetailActions = {
    select: setSelection,
    openVid,
    labelFor,
    toggleExpand: handleToggle,
    fetchRisk: (personId) => void fetchRisk(personId),
  }

  return (
    <main className="page page--flush explorer">
      <div className="explorer-topbar">
        <div className="row" style={{ flex: '0 0 auto', gap: 'var(--space-2)' }}>
          <strong>Investigation</strong>
          <div className="row" style={{ gap: 'var(--space-1)' }}>
            <button
              className={`btn btn-sm${mode === 'explore' ? ' btn--primary' : ''}`}
              onClick={() => setMode('explore')}
            >
              Explore
            </button>
            <button
              className={`btn btn-sm${mode === 'connect' ? ' btn--primary' : ''}`}
              onClick={() => setMode('connect')}
            >
              Verify connection
            </button>
          </div>
        </div>
        {mode === 'explore' ? (
          <>
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
            <label className="row" style={{ gap: 'var(--space-2)' }}>
              <span className="muted">Min confidence</span>
              <InfoTooltip text="How sure the link has to be before it counts. A value only these two people share scores high; one that forty people share scores near zero. Raising this also hides people you could only reach through a weak link." />
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
                // One request per drag, not one per step.
                onPointerUp={() => {
                  if (rootId) void loadNetwork(rootId, degree, { preserveExpanded: true })
                }}
                aria-label="Minimum link confidence"
              />
              <span className="muted" style={{ width: 32 }}>
                {minConfidence.toFixed(2)}
              </span>
            </label>
          </>
        ) : (
          <div className="row" style={{ gap: 'var(--space-3)', flex: 1 }}>
            <PersonSearchField
              label="Person A"
              placeholder="Search for a person…"
              selected={personA}
              onSelect={setPersonA}
            />
            <PersonSearchField
              label="Person B"
              placeholder="Search for a person…"
              selected={personB}
              onSelect={setPersonB}
            />
            <button
              className="btn btn--primary btn-sm"
              disabled={!personA || !personB || connectionLoading}
              onClick={handleFindConnection}
            >
              {connectionLoading ? 'Searching…' : 'Find connection'}
            </button>
          </div>
        )}
      </div>

      {mode === 'explore' && (status || searchError || graph.error) && (
        <div className="status-strip">{graph.error ?? searchError ?? status}</div>
      )}
      {mode === 'connect' && connectionError && <div className="status-strip">{connectionError}</div>}
      {notice.map((line) => (
        <div className="status-strip" key={line}>
          {line}
        </div>
      ))}

      <div className="explorer-body">
        {mode === 'connect' ? (
          connectionResult && personA && personB ? (
            <ConnectionChainView
              sourceLabel={personA.label || personA.entity_id}
              targetLabel={personB.label || personB.entity_id}
              result={connectionResult}
              onExplore={(personId) => void handleExploreFromConnection(personId)}
            />
          ) : (
            <div className="panel" style={{ margin: 'var(--space-4)' }}>
              <h3>Verify a connection</h3>
              <p className="text-secondary">
                Pick two people above and choose "Find connection" to see the strongest chain
                linking them — or confirm they aren't connected at all.
              </p>
            </div>
          )
        ) : (
        <>
        <div className="explorer-center">
          {view === '2d' ? (
            <GraphCanvas
              ref={canvas2DRef}
              nodes={graph.canvasNodes}
              edges={graph.canvasEdges}
              selectedVid={selectedVid}
              // The network's own root, not the `rootId` state: that is set
              // the instant a result is picked, while this is the person the
              // graph on screen was actually projected from.
              rootVid={graph.network?.root_id ?? null}
              mainTags={MAIN_TAGS}
              onSelect={(vid) => (vid ? openVid(vid) : setSelection(null))}
              onSelectEdge={handleSelectEdge}
              selectedEdge={selectedEdge}
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
              rootVid={graph.network?.root_id ?? null}
              mainTags={MAIN_TAGS}
              onSelect={(vid) => (vid ? openVid(vid) : setSelection(null))}
              onSelectEdge={handleSelectEdge}
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
          <DetailPanel
            selection={selection}
            network={graph.network}
            canvasNodes={graph.canvasNodes}
            data={detailData}
            actions={detailActions}
            risk={risk}
          />
        </div>
        </>
        )}
      </div>
    </main>
  )
}
