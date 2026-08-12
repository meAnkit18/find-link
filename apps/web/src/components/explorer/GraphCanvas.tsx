import { useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef, useCallback } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'
import {
  EDGE_COLOR,
  ROOT_COLOR,
  SELECT_COLOR,
  colorForDegree,
  colorForTag,
  edgeDegree,
  edgeId,
  edgeLabel,
  edgeWeight,
  isNewSinceFilterChange,
  nodeDegree,
  roleForNode,
} from './graphStyle'
import GraphPopup, { type GraphPopupInfo } from './GraphPopup'

cytoscape.use(fcose)

// Soft light gradient behind the canvas — cytoscape's own canvas stays
// transparent, so this is a plain CSS background underneath it.
const CANVAS_BG = 'radial-gradient(65% 65% at 50% 45%, #ffffff 0%, #eef0f4 100%)'

// Fallbacks for anything with no degree of its own: Explorer's whole graph,
// and Investigation's attribute spokes.
const PLAIN_EDGE_COLOR = 'rgba(100, 116, 139, 0.55)'
const PLAIN_ARROW_COLOR = 'rgba(100, 116, 139, 0.7)'

/** What a node is painted. Investigation's people carry a degree and are
 * colored by it; the root, the attribute sub-nodes, and every node on
 * Explorer have none and keep their tag color.
 *
 * Takes the two values rather than the element, so each style entry below
 * can stay an inline arrow — cytoscape's typings want the exact
 * NodeSingular/EdgeSingular parameter per property and won't accept one
 * shared signature. */
function paintForNode(degreeColor: string, tag: string): string {
  return degreeColor || colorForTag(tag)
}

const STYLE: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': (ele) => paintForNode(ele.data('degreeColor'), ele.data('tag')),
      label: 'data(label)',
      color: '#334155',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 6,
      width: 18,
      height: 18,
      'border-width': 1.5,
      'border-color': 'rgba(30, 41, 59, 0.3)',
      'text-outline-width': 2,
      'text-outline-color': '#ffffff',
    },
  },
  {
    // Attribute/sub nodes (phone, email, address, ...) render smaller and
    // muted, so hub-vs-attribute reads at a glance without reading labels.
    selector: 'node[role = "sub"]',
    style: {
      width: 10,
      height: 10,
      'font-size': 8,
      'border-width': 1,
      opacity: 0.75,
    },
  },
  {
    // Hub nodes carry a soft tag-colored halo (cytoscape's built-in overlay,
    // standing in for kindred's SVG blur filter glow).
    selector: 'node[role = "main"]',
    style: {
      'overlay-color': (ele) => paintForNode(ele.data('degreeColor'), ele.data('tag')),
      'overlay-opacity': 0.22,
      'overlay-padding': 10,
    },
  },
  {
    // Arrived with the last degree/confidence change. Marked with a dashed
    // dark outline rather than another color: the fill is already carrying
    // the degree, and "just appeared" is a temporary annotation on top of
    // that, not a category of its own.
    //
    // Declared before :selected and .node-root so both still win the
    // border — selection is what the user is doing right now, and the root
    // is never new anyway (it's degree 0 and present in every projection).
    selector: 'node.node-new',
    style: {
      'border-style': 'dashed',
      'border-width': 2.5,
      'border-color': '#0f172a',
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-color': SELECT_COLOR,
      'border-width': 3,
      'overlay-color': SELECT_COLOR,
      'overlay-opacity': 0.38,
      'overlay-padding': 12,
    },
  },
  {
    // The searched node — the root everything else on screen hangs off.
    // Marked permanently rather than only while selected, because selection
    // moves to whatever the user clicks next and the root has to stay
    // findable after that. Deliberately declared after `node:selected` so
    // the ring survives selection (see the combined rule below).
    //
    // The tag color stays on the fill so the legend keeps telling the truth
    // — the ring, the size and the weight of the label carry "this is the
    // one you searched for" instead.
    selector: 'node.node-root',
    style: {
      width: 30,
      height: 30,
      'border-width': 4,
      'border-color': ROOT_COLOR,
      'overlay-color': ROOT_COLOR,
      'overlay-opacity': 0.3,
      'overlay-padding': 14,
      'font-size': 13,
      'font-weight': 'bold',
      color: '#0f172a',
      'text-margin-y': 9,
      opacity: 1,
      'z-index': 10,
    },
  },
  {
    // Root and selected at once — which is the state right after a search.
    // Keep the gold ring that identifies the root and let the halo carry
    // the selection accent, so neither signal is lost.
    selector: 'node.node-root:selected',
    style: {
      'border-color': ROOT_COLOR,
      'border-width': 4,
      'overlay-color': SELECT_COLOR,
      'overlay-opacity': 0.42,
    },
  },
  {
    selector: 'edge',
    style: {
      // Investigation's person links carry a `weight` (how many separate
      // things two people share), so an overlap of three details reads as
      // visibly stronger than a single shared email. Everything else has
      // weight 1 and renders exactly as it always did.
      width: (ele: cytoscape.EdgeSingular) => 1.5 + Math.min(Number(ele.data('weight')) || 1, 5) - 1,
      // Colored by which hop out from the searched person this link was
      // found at, so 1st/2nd/3rd degree relationships read apart without
      // having to trace the path back by eye.
      'line-color': (ele) => ele.data('degreeColor') || PLAIN_EDGE_COLOR,
      'target-arrow-color': (ele: cytoscape.EdgeSingular) => ele.data('degreeColor') || PLAIN_ARROW_COLOR,
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      label: 'data(edgeType)',
      'font-size': 8,
      color: '#334155',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0,
      'text-background-padding': '2px',
      'text-opacity': 0,
    },
  },
  {
    // A person-to-attribute spoke is structure, not a finding: it should
    // recede so the person-to-person links stay the thing you read first.
    selector: 'edge.edge-spoke',
    style: {
      width: 1,
      'line-color': 'rgba(100, 116, 139, 0.3)',
      'line-style': 'dashed',
      'target-arrow-shape': 'none',
    },
  },
  {
    // The link half of the same "just appeared" marking. Dotted rather than
    // dashed so it can't be read as an attribute spoke, and it keeps its
    // degree color — this says when it arrived, not what it is. Declared
    // after edge-spoke so a spoke can never pick it up, and before the
    // hover/highlight rule so those still take over on interaction.
    selector: 'edge.edge-new',
    style: {
      'line-style': 'dotted',
      // Floor the width rather than fixing it: a dotted line needs some
      // weight to read, but overwriting the width outright would throw away
      // the via_count encoding on precisely the links being studied.
      width: (ele: cytoscape.EdgeSingular) =>
        Math.max(2.5, 1.5 + Math.min(Number(ele.data('weight')) || 1, 5) - 1),
    },
  },
  {
    // Relationship labels are only shown on demand (hover, or touching the
    // selected node) — permanently-visible edge labels were the biggest
    // source of visual clutter on any graph with more than a few edges.
    selector: 'edge.edge-hover, edge.edge-highlight',
    style: {
      'line-color': SELECT_COLOR,
      'target-arrow-color': SELECT_COLOR,
      width: 2,
      'text-opacity': 1,
      'text-background-opacity': 0.85,
    },
  },
  {
    // The link whose details are open in the panel. Declared last so it wins
    // over edge-highlight: both of a selected link's endpoints are also
    // "touching a selected node" as far as that rule is concerned, and the
    // one the user actually opened has to stand out from the pair.
    selector: 'edge.edge-selected',
    style: {
      'line-color': SELECT_COLOR,
      'target-arrow-color': SELECT_COLOR,
      width: 4,
      'overlay-color': SELECT_COLOR,
      'overlay-opacity': 0.25,
      'overlay-padding': 6,
      'text-opacity': 1,
      'text-background-opacity': 0.9,
    },
  },
]

/** Opt-in override for callers whose graph is small enough that the hop
 * reasons should always be readable. The rule above hides them because a
 * dense network of labels is unreadable — but a connection path is a
 * handful of edges that exist precisely to state why they exist, and
 * making the investigator hover each one to find out defeats the view.
 *
 * Appended after the base rules, and touches only label visibility — the
 * hover and selection rules own line colour and width, so highlighting
 * still reads exactly as it does on Explore. */
const ALWAYS_LABEL_EDGES: StylesheetStyle[] = [
  {
    selector: 'edge',
    style: {
      'text-opacity': 1,
      'text-background-opacity': 0.85,
      'font-size': 9,
    },
  },
]

// cy.fit() scales until the content fills the viewport, which on a
// three-node result means ~600% — labels the size of the canvas, and no
// room left for the nodes an expansion is about to add. Cap it.
const MAX_FIT_ZOOM = 1.6

function fitToElements(cy: Core) {
  cy.fit(undefined, 40)
  if (cy.zoom() > MAX_FIT_ZOOM) {
    cy.zoom(MAX_FIT_ZOOM)
    cy.center()
  }
}

/** If the graph has drifted entirely outside the viewport (the "black
 * screen"), bring it back into view; otherwise leave the camera alone. */
function ensureGraphVisible(cy: Core) {
  if (cy.nodes().length === 0) return
  const bb = cy.nodes().boundingBox()
  const ext = cy.extent()
  const overlaps = bb.x1 < ext.x2 && bb.x2 > ext.x1 && bb.y1 < ext.y2 && bb.y2 > ext.y1
  if (!overlaps) fitToElements(cy)
}

/** Re-frame when something the user just added landed outside the
 * viewport — an attribute ring, or the extra people a higher degree pulled
 * in. When the new nodes are already on screen the camera is left alone,
 * so this never yanks the view out from under a manual pan or zoom. */
function ensureAddedVisible(cy: Core, addedIds: string[]) {
  if (addedIds.length === 0 || cy.nodes().length === 0) return
  const ext = cy.extent()
  const offscreen = addedIds.some((id) => {
    const ele = cy.getElementById(id)
    if (ele.empty()) return false
    const { x, y } = ele.position()
    return x < ext.x1 || x > ext.x2 || y < ext.y1 || y > ext.y2
  })
  if (offscreen) fitToElements(cy)
}

/** Shared fcose tuning for both the initial/incremental layout (data-sync
 * effect) and the manual "re-run layout" control — kept in one place so the
 * two call sites can't drift out of sync. Wider spacing than fcose's
 * defaults so nodes don't visually overlap once there are more than a
 * handful on screen.
 *
 * quality stays "default" on every path. "draft" applies the spectral layout
 * and nothing else — the force phase never runs, so nodeRepulsion and
 * idealEdgeLength below are ignored and nothing pushes overlapping nodes
 * apart. On a star-shaped graph (one searched person plus everyone they
 * connect to) the spectral embedding piles the leaves on top of each other,
 * which is what made a fresh search land as a squished clump until the first
 * expansion happened to re-run the layout at "default".
 *
 * `randomize` still varies: true seeds from a spectral placement (a brand new
 * graph, where the current coordinates mean nothing), false refines the
 * positions already on screen (an expansion, where reshuffling everything
 * would lose the picture the user is reading). Note fcose only supports
 * `randomize: false` with quality "default"/"proof" — the pairing this
 * function now always satisfies, where "draft" used to throw inside
 * relocateComponent() because spectralResult is never populated with
 * randomize off. */
function fcoseLayoutOptions(randomize: boolean, spread = 1) {
  return {
    name: 'fcose',
    animate: false,
    quality: 'default',
    fit: false,
    nodeRepulsion: 12000 * spread,
    idealEdgeLength: 130 * spread,
    randomize,
  }
}

/** Run the force layout over the nodes that are free to move, leaving
 * pinned ones (Investigation's radially-placed attribute rings) exactly
 * where the caller put them. With nothing pinned this is the whole graph,
 * i.e. identical to `cy.layout(...)`. */
function layoutFreeNodes(cy: Core, pinned: Map<string, cytoscape.Position>, randomize: boolean) {
  const free = pinned.size === 0 ? cy.nodes() : cy.nodes().filter((ele) => !pinned.has(ele.id()))
  const elements = free.union(free.edgesWith(free))
  // Rings need somewhere to go: when children are pinned around these
  // nodes, push the nodes themselves further apart so each has room for
  // its own ring. Without pinned children this is the layout as it was.
  const spread = pinned.size > 0 ? 2 : 1
  // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
  // @types/cytoscape's built-in layout typings, hence the cast.
  return elements.layout(fcoseLayoutOptions(randomize, spread) as unknown as cytoscape.LayoutOptions)
}

/** Move pinned nodes onto their given positions. They stay unlocked/
 * draggable — the force layout still leaves them alone (it only ever runs
 * over the free-node collection, built by excluding this same `pinned` map
 * in layoutFreeNodes) — so a user's manual nudge sticks until the caller
 * recomputes their position itself (e.g. the ring's parent moves). */
function applyPinnedPositions(cy: Core, pinned: Map<string, cytoscape.Position>) {
  cy.batch(() => {
    for (const [id, position] of pinned) {
      const ele = cy.getElementById(id)
      if (ele.empty()) continue
      ele.position({ ...position })
    }
  })
}

export interface GraphCanvasHandle {
  zoomIn: () => void
  zoomOut: () => void
  fit: () => void
  centerSelected: () => void
  relayout: () => void
  exportPng: () => void
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  /** The node the user searched for. Ringed and enlarged for as long as
   * that search stands, independently of `selectedVid` — selection follows
   * every click, this doesn't. Omit for no root marking. */
  rootVid?: string | null
  /** Tags that count as "main" hub nodes. Empty = no hierarchy — every
   * node renders identically (Explorer's default, unchanged behavior). */
  mainTags: Set<string>
  onSelect: (vid: string | null) => void
  /** Fired on every edge tap, with the edge's two endpoints. The caller
   * decides what that means — Investigation opens the relationship in its
   * detail panel, and resolves a person-to-attribute spoke to the attribute
   * instead. Omit to leave edges un-selectable (Explorer's behavior). */
  onSelectEdge?: (source: string, target: string) => void
  /** The link currently open in the caller's detail panel, so the arrow
   * carrying it reads as selected. Endpoint order doesn't matter. */
  selectedEdge?: { source: string; target: string } | null
  /** Fired on every node tap. The caller decides expand vs. collapse based
   * on its own expanded-state tracking (single click toggles both). */
  onToggleExpand: (vid: string) => void
  /** Show every edge's label without hovering. For small, deliberately
   * chosen graphs (the connection path); read once when the canvas is
   * created, so it is a per-mount option rather than a live toggle. */
  alwaysLabelEdges?: boolean
  onZoomChange?: (zoom: number) => void
  /** Nodes the caller places itself — Investigation's radial attribute
   * rings. These are excluded from the force layout, though still
   * draggable (see onChildMoved). Omit for the default behavior:
   * everything is laid out by fcose. */
  pinnedPositions?: Map<string, cytoscape.Position>
  /** Fired while a hub node is dragged, so a caller pinning children
   * around it can keep the ring centred on its parent. */
  onParentMoved?: (vid: string, position: cytoscape.Position) => void
  /** Fired while a pinned node itself (e.g. an attribute in a ring) is
   * dragged, so a caller can remember the user's manual placement instead
   * of snapping it back to the computed ring position. */
  onChildMoved?: (vid: string, position: cytoscape.Position) => void
  /** Fired once the force layout settles, with where every node landed —
   * what a caller needs before it can place anything relative to them. */
  onPositionsSettled?: (positions: Map<string, cytoscape.Position>) => void
}

const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  {
    nodes,
    edges,
    selectedVid,
    rootVid,
    mainTags,
    onSelect,
    onSelectEdge,
    selectedEdge,
    onToggleExpand,
    alwaysLabelEdges = false,
    onZoomChange,
    pinnedPositions,
    onParentMoved,
    onChildMoved,
    onPositionsSettled,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  // Last known position of every node that has ever been shown, so filter
  // toggles restore nodes where they were instead of dropping them at (0,0)
  // off-screen and re-running the layout.
  const positionsRef = useRef<Map<string, cytoscape.Position>>(new Map())
  const onSelectRef = useRef(onSelect)
  const onSelectEdgeRef = useRef(onSelectEdge)
  onSelectEdgeRef.current = onSelectEdge
  const onToggleExpandRef = useRef(onToggleExpand)
  const onParentMovedRef = useRef(onParentMoved)
  const onChildMovedRef = useRef(onChildMoved)
  const onPositionsSettledRef = useRef(onPositionsSettled)
  onPositionsSettledRef.current = onPositionsSettled
  onSelectRef.current = onSelect
  onToggleExpandRef.current = onToggleExpand
  onParentMovedRef.current = onParentMoved
  onChildMovedRef.current = onChildMoved

  const emptyPinned = useMemo(() => new Map<string, cytoscape.Position>(), [])
  const pinnedNodes = pinnedPositions ?? emptyPinned
  // Read by the mount-time event handlers and the imperative relayout(),
  // which both outlive any single render.
  const pinnedPositionsRef = useRef(pinnedNodes)
  pinnedPositionsRef.current = pinnedNodes
  // Expanding a person needs room the current layout doesn't have, so the
  // hub nodes are re-spread once per expansion. Tracked by count: a ring
  // that only moved must not trigger another reflow, or this never settles.
  const pinnedCountRef = useRef(0)

  const [popupInfo, setPopupInfo] = useState<GraphPopupInfo | null>(null)
  const [pinned, setPinned] = useState(false)
  const pinnedRef = useRef(pinned)
  pinnedRef.current = pinned
  const closePopup = () => {
    setPinned(false)
    setPopupInfo(null)
  }

  const nodePopupInfo = (ele: cytoscape.NodeSingular): GraphPopupInfo => ({
    kind: 'node',
    label: ele.data('label'),
    tag: ele.data('tag'),
    color: colorForTag(ele.data('tag')),
    role: ele.data('role'),
  })
  const edgePopupInfo = (ele: cytoscape.EdgeSingular): GraphPopupInfo => ({
    kind: 'edge',
    label: ele.data('edgeType'),
    source: ele.source().data('label') ?? ele.data('source'),
    target: ele.target().data('label') ?? ele.data('target'),
    color: EDGE_COLOR,
  })

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      style: alwaysLabelEdges ? [...STYLE, ...ALWAYS_LABEL_EDGES] : STYLE,
      wheelSensitivity: 0.2,
      pixelRatio: 1,
      // NOTE: textureOnViewport was removed on purpose — it causes blank /
      // black frames during pan+zoom on some GPUs and isn't needed here.
      hideEdgesOnViewport: true,
      motionBlur: false,
    })
    cyRef.current = cy

    // Single click both selects (opens the detail panel) and toggles
    // expand/collapse — approved interaction model, applies to any node.
    // It also pins the hover popup, matching kindred's click-to-pin.
    cy.on('tap', 'node', (evt) => {
      const vid = evt.target.id()
      onSelectRef.current(vid)
      onToggleExpandRef.current(vid)
      setPopupInfo(nodePopupInfo(evt.target))
      setPinned(true)
    })
    cy.on('tap', 'edge', (evt) => {
      onSelectEdgeRef.current?.(evt.target.data('source'), evt.target.data('target'))
      setPopupInfo(edgePopupInfo(evt.target))
      setPinned(true)
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectRef.current(null)
        closePopup()
      }
    })
    // Keep the position cache fresh when the user drags nodes around.
    cy.on('dragfree', 'node', (evt) => {
      positionsRef.current.set(evt.target.id(), { ...evt.target.position() })
    })
    // A dragged hub carries its pinned children with it, so an attribute
    // ring stays centred on the person it belongs to. A dragged pinned node
    // (an attribute already sitting in a ring) instead reports its own
    // manual placement, so the caller can nudge it without the ring
    // snapping it straight back.
    cy.on('drag', 'node', (evt) => {
      const vid = evt.target.id()
      if (pinnedPositionsRef.current.has(vid)) {
        onChildMovedRef.current?.(vid, { ...evt.target.position() })
        return
      }
      onParentMovedRef.current?.(vid, { ...evt.target.position() })
    })
    cy.on('mouseover', 'node', (evt) => {
      if (!pinnedRef.current) setPopupInfo(nodePopupInfo(evt.target))
    })
    cy.on('mouseout', 'node', () => {
      if (!pinnedRef.current) setPopupInfo(null)
    })
    cy.on('mouseover', 'edge', (evt) => {
      evt.target.addClass('edge-hover')
      if (!pinnedRef.current) setPopupInfo(edgePopupInfo(evt.target))
    })
    cy.on('mouseout', 'edge', (evt) => {
      evt.target.removeClass('edge-hover')
      if (!pinnedRef.current) setPopupInfo(null)
    })

    // Cytoscape caches its container's size and offset. The container
    // changes size whenever the detail panel opens/closes, the filter panel
    // mounts, or the window resizes — without this, rendering goes stale
    // (blank areas) and clicks hit the wrong coordinates.
    const resizeObserver = new ResizeObserver(() => cy.resize())
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  const handleZoomChange = useCallback(() => {
    const cy = cyRef.current
    if (cy) onZoomChange?.(cy.zoom())
  }, [onZoomChange])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !onZoomChange) return
    cy.on('zoom', handleZoomChange)
    return () => { cy.off('zoom', handleZoomChange) }
  }, [onZoomChange, handleZoomChange])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        const cy = cyRef.current
        if (!cy) return
        cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
      },
      zoomOut: () => {
        const cy = cyRef.current
        if (!cy) return
        cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
      },
      fit: () => cyRef.current?.fit(undefined, 40),
      centerSelected: () => cyRef.current?.fit(cyRef.current.$('node:selected'), 40),
      relayout: () => {
        const cy = cyRef.current
        if (!cy) return
        layoutFreeNodes(cy, pinnedPositionsRef.current, false).run()
      },
      exportPng: () => {
        const cy = cyRef.current
        if (!cy) return
        const blob = cy.png({ output: 'blob', bg: '#ffffff', full: true })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'graph.png'
        a.click()
        URL.revokeObjectURL(url)
      },
    }),
    [],
  )

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const desiredNodeIds = new Set(nodes.map((n) => n.vid))
    const desiredEdgeIds = new Set(edges.map(edgeId))

    cy.edges().forEach((ele) => {
      if (!desiredEdgeIds.has(ele.id())) ele.remove()
    })
    cy.nodes().forEach((ele) => {
      if (!desiredNodeIds.has(ele.id())) {
        // Remember where the node was so re-showing it restores the spot.
        positionsRef.current.set(ele.id(), { ...ele.position() })
        ele.remove()
      }
    })

    let brandNewCount = 0
    const newNodeEles: ElementDefinition[] = []
    for (const n of nodes) {
      if (!cy.getElementById(n.vid).empty()) continue
      // A pinned node already has the position the caller wants; it must not
      // count as "brand new", or adding one attribute would re-run the force
      // layout and reshuffle every person on the canvas.
      const placed = pinnedNodes.get(n.vid) ?? positionsRef.current.get(n.vid)
      if (!placed) brandNewCount++
      newNodeEles.push({
        data: {
          id: n.vid,
          label: n.label,
          tag: n.tags[0] ?? 'entity',
          role: roleForNode(n, mainTags),
          // '' rather than null so the style functions can treat "no degree"
          // as plain falsy and fall through to the tag color.
          degreeColor: colorForDegree(nodeDegree(n)) ?? '',
        },
        ...(placed ? { position: { ...placed } } : {}),
      })
    }

    const newEdgeEles: ElementDefinition[] = edges
      .filter((e) => cy.getElementById(edgeId(e)).empty())
      .map((e) => ({
        data: {
          id: edgeId(e),
          source: e.src,
          target: e.dst,
          edgeType: edgeLabel(e),
          weight: edgeWeight(e),
          degreeColor: colorForDegree(edgeDegree(e)) ?? '',
        },
        ...(pinnedNodes.has(e.src) || pinnedNodes.has(e.dst) ? { classes: 'edge-spoke' } : {}),
      }))

    cy.add([...newNodeEles, ...newEdgeEles])

    // Keep already-visible nodes' main/sub role in sync when mainTags
    // changes (e.g. the user just marked a tag as main), and already-visible
    // edges' labels in sync when a later expansion brings back the real
    // relationship_type for an edge that was first added without one (e.g.
    // from /overview) — without touching anything else about them, and
    // without writing when the value hasn't actually changed (Cytoscape's
    // data setter forces a style recalculation on every call).
    for (const n of nodes) {
      const ele = cy.getElementById(n.vid)
      if (ele.empty()) continue
      const role = roleForNode(n, mainTags)
      if (ele.data('role') !== role) ele.data('role', role)
      // Raising the degree control re-projects the network, and a person
      // who was 2 hops out can come back as 1 — so this has to re-sync, not
      // just be set once when the node is added.
      const degreeColor = colorForDegree(nodeDegree(n)) ?? ''
      if (ele.data('degreeColor') !== degreeColor) ele.data('degreeColor', degreeColor)
      const isNew = isNewSinceFilterChange(n)
      if (isNew !== ele.hasClass('node-new')) ele.toggleClass('node-new', isNew)
      // Carried as a class rather than a data field: it's purely a styling
      // flag, and toggleClass is a no-op when the value already matches,
      // where `.data()` forces a style recalculation on every call.
      const isRoot = n.vid === rootVid
      if (isRoot !== ele.hasClass('node-root')) ele.toggleClass('node-root', isRoot)
    }
    for (const e of edges) {
      const ele = cy.getElementById(edgeId(e))
      if (ele.empty()) continue
      const label = edgeLabel(e)
      if (ele.data('edgeType') !== label) ele.data('edgeType', label)
      const weight = edgeWeight(e)
      if (ele.data('weight') !== weight) ele.data('weight', weight)
      const degreeColor = colorForDegree(edgeDegree(e)) ?? ''
      if (ele.data('degreeColor') !== degreeColor) ele.data('degreeColor', degreeColor)
      const isNew = isNewSinceFilterChange(e)
      if (isNew !== ele.hasClass('edge-new')) ele.toggleClass('edge-new', isNew)
      // An edge can gain a pinned endpoint after it was added (the user just
      // expanded one of its people), which turns it into an attribute spoke.
      const isSpoke = pinnedNodes.has(e.src) || pinnedNodes.has(e.dst)
      if (isSpoke !== ele.hasClass('edge-spoke')) ele.toggleClass('edge-spoke', isSpoke)
    }

    // Only run the layout when nodes appear that have never had a position
    // (initial load, an expansion, a search hit). Re-showing filtered nodes
    // and toggling edge types keep the existing layout untouched, so the
    // graph no longer reshuffles on every filter click.
    const addedIds = newNodeEles.map((ele) => String(ele.data.id))
    const pinnedGrew = pinnedNodes.size > pinnedCountRef.current
    pinnedCountRef.current = pinnedNodes.size

    // Whether there is anything on the canvas worth laying out *from*. This
    // has to be read after the sync above, not before it: a new search prunes
    // every old node and adds a whole new set, so looking at the canvas
    // beforehand sees the outgoing graph and wrongly concludes there are
    // positions to refine — leaving fcose to run its force phase over a pile
    // of brand new nodes all stacked at (0, 0). Counted after cy.add, the
    // survivors plus the nodes restored from the position cache are exactly
    // the nodes that do have somewhere to start.
    const positionedCount = cy.nodes().length - brandNewCount
    const isFreshLayout = positionedCount === 0

    /** Cache where everything settled, re-seat the rings, and tell the
     * caller — which lets it recompute rings against the new positions. */
    const afterLayout = () => {
      cy.nodes().forEach((ele) => { positionsRef.current.set(ele.id(), { ...ele.position() }) })
      applyPinnedPositions(cy, pinnedNodes)
      onPositionsSettledRef.current?.(new Map(positionsRef.current))
    }

    if (brandNewCount > 0) {
      const layout = layoutFreeNodes(cy, pinnedNodes, isFreshLayout)
      layout.one('layoutstop', () => {
        afterLayout()
        if (isFreshLayout) fitToElements(cy)
        else {
          ensureGraphVisible(cy)
          ensureAddedVisible(cy, addedIds)
        }
      })
      layout.run()
    } else if (pinnedGrew) {
      // Someone's details just opened. Their ring is already placed from
      // the old positions; re-spread the people so it has somewhere to go,
      // then re-frame on the result.
      applyPinnedPositions(cy, pinnedNodes)
      const layout = layoutFreeNodes(cy, pinnedNodes, false)
      layout.one('layoutstop', () => {
        afterLayout()
        fitToElements(cy)
      })
      layout.run()
    } else {
      applyPinnedPositions(cy, pinnedNodes)
      if (newNodeEles.length > 0 || newEdgeEles.length > 0) {
        ensureGraphVisible(cy)
        ensureAddedVisible(cy, addedIds)
      }
    }
  }, [nodes, edges, mainTags, pinnedNodes, rootVid])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().unselect()
    cy.edges().removeClass('edge-highlight edge-selected')
    if (selectedVid) {
      const node = cy.getElementById(selectedVid)
      node.select()
      node.connectedEdges().addClass('edge-highlight')
    }
    if (selectedEdge) {
      // Matched by endpoints rather than by edge id: the panel identifies a
      // projected link by the pair of people it joins, and the projection
      // emits it in whichever direction it was found.
      const { source, target } = selectedEdge
      cy.edges()
        .filter(
          (ele) =>
            (ele.data('source') === source && ele.data('target') === target) ||
            (ele.data('source') === target && ele.data('target') === source),
        )
        .addClass('edge-selected')
    }
  }, [selectedVid, selectedEdge])

  // Tag breakdown for the bottom legend bar, mirroring kindred's persistent
  // node-kind legend (there it's a fixed 4-kind list; here tags are
  // schema-driven, so this is the top tags actually present, by count).
  const legend = useMemo(() => {
    const counts = new Map<string, number>()
    for (const n of nodes) {
      // Only nodes actually painted by their tag belong in the tag half of
      // the legend. Anything carrying a degree is painted by that instead,
      // and is accounted for by `degreeLegend` below — without this the bar
      // would swear "person" is pink while every person on screen is
      // violet, teal or crimson.
      if (nodeDegree(n) !== null) continue
      const tag = n.tags[0] ?? 'entity'
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
  }, [nodes])

  /** How many people sit at each distance from the searched person. Empty
   * on Explorer, whose nodes carry no degree — which is what keeps the
   * degree half of the legend off a page where it would mean nothing.
   *
   * This doubles as the relief the contrast check requires: the 3rd-degree
   * hue clears 3:1 against the canvas, but naming the colors here is what
   * stops degree from being encoded by color alone. */
  const degreeLegend = useMemo(() => {
    const counts = new Map<number, number>()
    for (const n of nodes) {
      const degree = nodeDegree(n)
      if (degree === null) continue
      counts.set(degree, (counts.get(degree) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => a[0] - b[0])
  }, [nodes])

  /** How many people the last filter change brought in. Zero on a fresh
   * search and on Explorer, which is what keeps the entry out of the bar
   * unless it has something to say. */
  const newCount = useMemo(() => nodes.filter(isNewSinceFilterChange).length, [nodes])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <div className="graph-surface" style={{ position: 'relative', flex: 1, minHeight: 0, background: CANVAS_BG }}>
        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
        <GraphPopup info={popupInfo} pinned={pinned} onClose={closePopup} />
      </div>
      <div className="graph-legend">
        {degreeLegend.map(([degree, count]) => (
          <span key={`degree-${degree}`} className="graph-legend__item">
            <span
              className={`graph-legend__dot${degree === 0 ? ' graph-legend__dot--root' : ''}`}
              style={{ background: colorForDegree(degree) ?? colorForTag('person') }}
            />
            {degree === 0 ? 'searched' : `${degree}° away`} ({count})
          </span>
        ))}
        {newCount > 0 && (
          <span className="graph-legend__item">
            <span className="graph-legend__dot graph-legend__dot--new" />
            new since last filter ({newCount})
          </span>
        )}
        {degreeLegend.length > 0 && legend.length > 0 && <span className="graph-legend__divider" />}
        {legend.map(([tag, count]) => (
          <span key={tag} className="graph-legend__item">
            <span className="graph-legend__dot" style={{ background: colorForTag(tag) }} />
            {tag} ({count})
          </span>
        ))}
        <span className="graph-legend__spacer" />
        <span>
          {nodes.length} node{nodes.length === 1 ? '' : 's'} · {edges.length} link{edges.length === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  )
})

export default GraphCanvas
