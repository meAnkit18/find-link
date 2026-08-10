import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import ForceGraph3D, { type ForceGraphMethods, type NodeObject, type LinkObject } from 'react-force-graph-3d'
import * as THREE from 'three'
import type { GraphEdge, GraphNode } from '../../api/types'
import {
  EDGE_COLOR,
  ROOT_COLOR,
  SELECT_COLOR,
  colorForDegree,
  colorForTag,
  edgeDegree,
  edgeLabel,
  isNewSinceFilterChange,
  nodeDegree,
  roleForNode,
  type NodeRole,
} from './graphStyle'
import type { GraphCanvasHandle } from './GraphCanvas'
import GraphPopup, { type GraphPopupInfo } from './GraphPopup'

interface Node3D {
  id: string
  label: string
  tag: string
  role: NodeRole
  color: string
  val: number
  isRoot: boolean
  /** Arrived with the last degree/confidence change. */
  isNew: boolean
}

interface Link3D {
  // react-force-graph mutates these from ids into resolved node objects
  // once the simulation has run, hence the union.
  source: string | Node3D
  target: string | Node3D
  label: string
  /** Degree color for a person link, or the plain edge gray for an
   * attribute spoke, which is at no degree at all. */
  color: string
  /** Arrived with the last degree/confidence change. */
  isNew: boolean
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  /** The node the user searched for — rendered larger with a gold halo and
   * label for as long as that search stands. See GraphCanvas's prop of the
   * same name; this is the 3D counterpart of its ring. */
  rootVid?: string | null
  mainTags: Set<string>
  onSelect: (vid: string | null) => void
  /** Fired on every link click, with the link's endpoints — the 3D
   * counterpart of GraphCanvas's prop of the same name, so switching views
   * doesn't switch off relationship selection. */
  onSelectEdge?: (source: string, target: string) => void
  onToggleExpand: (vid: string) => void
  /** child node id -> the expanded parents it hangs off. Given these, the
   * children are held in a ring around their parent instead of being pushed
   * around by the force simulation — the 3D counterpart of the 2D canvas's
   * pinned radial layout. A child with two parents sits between them. */
  ringParents?: Map<string, string[]>
}

const RING_RADIUS = 26
const RING_SPACING = 13

interface RingSlot {
  parentIds: string[]
  index: number
  count: number
}

/** A Node3D after the simulation has attached coordinates to it. fx/fy/fz
 * are d3-force's "hold this node here" fields. */
type SimNode = Node3D & {
  x?: number
  y?: number
  z?: number
  fx?: number
  fy?: number
  fz?: number
}

/* ---- world-space text sprites, ported from kindred-main's graph-3d.tsx ---- */
function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

/** `dashed` draws the chip's outline as a heavier dashed rule — the 3D
 * stand-in for the dashed node border the 2D canvas puts on nodes that
 * arrived with the last filter change. There is no border to dash on a
 * sphere, so the label chip carries the marking instead. */
function makeTextTexture(
  text: string,
  ink: string,
  dashed = false,
): { tex: THREE.CanvasTexture; aspect: number } {
  const dpr = 2
  const fontPx = 30
  const padX = 13
  const padY = 8
  const font = `600 ${fontPx}px -apple-system, "Helvetica Neue", Arial, sans-serif`
  const measure = document.createElement('canvas').getContext('2d')!
  measure.font = font
  const tw = Math.ceil(measure.measureText(text).width)
  const w = tw + padX * 2
  const h = fontPx + padY * 2
  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(w * dpr)
  canvas.height = Math.ceil(h * dpr)
  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)
  ctx.fillStyle = 'rgba(255,255,255,0.85)'
  roundRectPath(ctx, 0.75, 0.75, w - 1.5, h - 1.5, h / 2)
  ctx.fill()
  ctx.lineWidth = dashed ? 2.5 : 1
  ctx.strokeStyle = dashed ? '#0f172a' : 'rgba(15,23,42,0.12)'
  if (dashed) ctx.setLineDash([7, 5])
  roundRectPath(ctx, 0.75, 0.75, w - 1.5, h - 1.5, h / 2)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.font = font
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'center'
  ctx.fillStyle = ink
  ctx.fillText(text, w / 2, h / 2 + 1)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.minFilter = THREE.LinearFilter
  tex.needsUpdate = true
  return { tex, aspect: w / h }
}

function hexToRgba(hex: string, a: number) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

function makeGlowTexture(color: string): THREE.CanvasTexture {
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const grd = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  grd.addColorStop(0, hexToRgba(color, 0.9))
  grd.addColorStop(0.2, hexToRgba(color, 0.5))
  grd.addColorStop(0.5, hexToRgba(color, 0.16))
  grd.addColorStop(1, hexToRgba(color, 0))
  ctx.fillStyle = grd
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.needsUpdate = true
  return tex
}

const GraphCanvas3D = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas3D(
  { nodes, edges, selectedVid, rootVid, mainTags, onSelect, onSelectEdge, onToggleExpand, ringParents },
  ref,
) {
  const fgRef = useRef<ForceGraphMethods<Node3D, Link3D>>()
  const wrapRef = useRef<HTMLDivElement>(null)
  const selectedVidRef = useRef(selectedVid)
  selectedVidRef.current = selectedVid

  // react-force-graph-3d has no ResizeObserver of its own — left to its
  // defaults it reads the container's size once and never adapts, so a
  // window resize, a fullscreen toggle, or a dragged panel splitter leaves
  // it stale (cropped or with dead space) until the next full remount.
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setSize({ width: el.clientWidth, height: el.clientHeight })
    update()
    const resizeObserver = new ResizeObserver(update)
    resizeObserver.observe(el)
    return () => resizeObserver.disconnect()
  }, [])

  const [labelsOn, setLabelsOn] = useState(true)
  const labelsRef = useRef(labelsOn)
  labelsRef.current = labelsOn
  const [popupInfo, setPopupInfo] = useState<GraphPopupInfo | null>(null)
  const [pinned, setPinned] = useState(false)
  const pinnedRef = useRef(pinned)
  pinnedRef.current = pinned
  const closePopup = () => {
    setPinned(false)
    setPopupInfo(null)
  }

  const nodeSprites = useRef<Map<string, THREE.Sprite>>(new Map())
  const glowTex = useRef<Map<string, THREE.CanvasTexture>>(new Map())
  const edgeSprites = useRef<THREE.Sprite[]>([])
  const textures = useRef<THREE.CanvasTexture[]>([])

  const graphData = useMemo(() => {
    const graphNodes: Node3D[] = nodes.map((n) => {
      const role = roleForNode(n, mainTags)
      const tag = n.tags[0] ?? 'entity'
      const isRoot = n.vid === rootVid
      return {
        id: n.vid,
        label: n.label,
        tag,
        role,
        // Degree first, tag color as the fallback — matching the 2D canvas,
        // where a person is painted by how far out they are and everything
        // without a degree keeps its tag color.
        color: colorForDegree(nodeDegree(n)) ?? colorForTag(tag),
        // The 3D stand-in for the 2D canvas's enlarged root: `val` drives
        // the sphere radius, so the searched node reads as the biggest
        // thing on screen from any camera angle.
        val: isRoot ? 14 : role === 'main' ? 6 : 2,
        isRoot,
        isNew: isNewSinceFilterChange(n),
      }
    })
    const graphLinks: Link3D[] = edges.map((e) => ({
      source: e.src,
      target: e.dst,
      label: edgeLabel(e),
      color: colorForDegree(edgeDegree(e)) ?? EDGE_COLOR,
      isNew: isNewSinceFilterChange(e),
    }))
    return { nodes: graphNodes, links: graphLinks }
  }, [nodes, edges, mainTags, rootVid])

  /** Each ring child's slot: which parents it hangs off, and its position
   * within that parent's ring. Sorted by id so the ring is stable across
   * re-renders instead of reshuffling every tick. */
  const ringSlots = useMemo(() => {
    const slots = new Map<string, RingSlot>()
    if (!ringParents || ringParents.size === 0) return slots
    const byParentKey = new Map<string, string[]>()
    for (const [childId, parentIds] of ringParents) {
      const key = [...parentIds].sort().join('|')
      const group = byParentKey.get(key)
      if (group) group.push(childId)
      else byParentKey.set(key, [childId])
    }
    for (const [key, children] of byParentKey) {
      children.sort()
      const parentIds = key.split('|')
      children.forEach((childId, index) => {
        slots.set(childId, { parentIds, index, count: children.length })
      })
    }
    return slots
  }, [ringParents])

  const holdRings = useCallback(() => {
    if (ringSlots.size === 0) return
    // react-force-graph mutates the very node objects we hand it, writing
    // x/y/z each tick and honoring fx/fy/fz as fixed positions.
    const byId = new Map((graphData.nodes as SimNode[]).map((n) => [n.id, n]))
    for (const [childId, slot] of ringSlots) {
      const child = byId.get(childId)
      if (!child) continue
      const anchors = slot.parentIds
        .map((id) => byId.get(id))
        .filter((p): p is SimNode => p != null && p.x != null)
      if (anchors.length === 0) continue
      if (anchors.length > 1) {
        // Shared by several expanded people: it's the reason they're
        // linked, so it belongs between them.
        child.fx = anchors.reduce((sum, p) => sum + (p.x ?? 0), 0) / anchors.length
        child.fy = anchors.reduce((sum, p) => sum + (p.y ?? 0), 0) / anchors.length
        child.fz = anchors.reduce((sum, p) => sum + (p.z ?? 0), 0) / anchors.length
        continue
      }
      const parent = anchors[0]
      const radius = Math.max(RING_RADIUS, (slot.count * RING_SPACING) / (2 * Math.PI))
      const angle = (slot.index / slot.count) * 2 * Math.PI
      child.fx = (parent.x ?? 0) + radius * Math.cos(angle)
      child.fy = (parent.y ?? 0) + radius * Math.sin(angle)
      child.fz = parent.z ?? 0
    }
  }, [ringSlots, graphData])

  // Same tag breakdown as the 2D canvas's bottom legend bar.
  const legend = useMemo(() => {
    const counts = new Map<string, number>()
    for (const n of nodes) {
      const tag = n.tags[0] ?? 'entity'
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8)
  }, [nodes])

  // fresh sprite registries whenever the dataset changes
  useEffect(() => {
    nodeSprites.current.clear()
    edgeSprites.current = []
  }, [graphData])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        const fg = fgRef.current
        if (!fg) return
        const { x, y, z } = fg.camera().position
        fg.cameraPosition({ x: x * 0.8, y: y * 0.8, z: z * 0.8 }, undefined, 300)
      },
      zoomOut: () => {
        const fg = fgRef.current
        if (!fg) return
        const { x, y, z } = fg.camera().position
        fg.cameraPosition({ x: x * 1.25, y: y * 1.25, z: z * 1.25 }, undefined, 300)
      },
      fit: () => {
        fgRef.current?.zoomToFit(400, 40)
      },
      centerSelected: () => {
        const vid = selectedVidRef.current
        if (!vid) return
        fgRef.current?.zoomToFit(400, 80, (node) => node.id === vid)
      },
      relayout: () => {
        fgRef.current?.d3ReheatSimulation()
      },
      exportPng: () => {
        const fg = fgRef.current
        if (!fg) return
        const url = fg.renderer().domElement.toDataURL('image/png')
        const a = document.createElement('a')
        a.href = url
        a.download = 'graph-3d.png'
        a.click()
      },
    }),
    [],
  )

  // dispose GPU textures on unmount
  useEffect(
    () => () => {
      for (const t of textures.current) t.dispose()
      textures.current = []
    },
    [],
  )

  // Per-node decoration: a floating label (sharpens as you zoom in) plus —
  // only for "main" hub nodes — a soft additive halo in the tag's color, so
  // the glow highlights the same nodes the 2D canvas's overlay glow does.
  // The selected node's halo switches to the accent color.
  const nodeThreeObject = useCallback((node: NodeObject<Node3D>) => {
    const group = new THREE.Group()
    if (!node.label) return group

    // Root wins the label ink even while selected, mirroring the 2D canvas
    // where the gold ring survives selection — the halo below is what
    // switches to the selection accent instead.
    const ink = node.isRoot ? ROOT_COLOR : node.id === selectedVidRef.current ? SELECT_COLOR : node.color
    const { tex, aspect } = makeTextTexture(node.label, ink, node.isNew)
    textures.current.push(tex)
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.95 }))
    const wh = node.isRoot ? 5.6 : node.role === 'main' ? 4.2 : 3.2
    const radius = Math.cbrt(Math.max(0.1, node.val ?? 2)) * 4
    label.scale.set(wh * aspect, wh, 1)
    label.position.set(0, radius + wh * 0.5 + 1.8, 0)
    label.raycast = () => {}
    label.visible = labelsRef.current
    group.add(label)
    nodeSprites.current.set(node.id, label)

    if (node.isRoot || node.role === 'main' || node.id === selectedVidRef.current) {
      const color = node.id === selectedVidRef.current
        ? SELECT_COLOR
        : node.isRoot
          ? ROOT_COLOR
          : node.color
      let gt = glowTex.current.get(color)
      if (!gt) {
        gt = makeGlowTexture(color)
        textures.current.push(gt)
        glowTex.current.set(color, gt)
      }
      const halo = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: gt, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }),
      )
      const hs = radius * (node.id === selectedVidRef.current ? 6.5 : 5)
      halo.scale.set(hs, hs, 1)
      halo.raycast = () => {}
      group.add(halo)
    }
    return group
  }, [])

  // Small label at each edge midpoint — the relationship type, colour-matched
  // to the shared edge accent. Kept as a real Object3D extension (not a
  // manual raycast hack) so react-force-graph-3d's own onLinkHover/onLinkClick
  // keep working against the underlying line.
  const linkThreeObject = useCallback((link: LinkObject<Node3D, Link3D>) => {
    const { tex, aspect } = makeTextTexture(link.label, link.color ?? EDGE_COLOR)
    textures.current.push(tex)
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.9 })
    const wh = 2.6
    const s = new THREE.Sprite(mat)
    s.scale.set(wh * aspect, wh, 1)
    s.raycast = () => {}
    s.visible = labelsRef.current
    edgeSprites.current.push(s)
    return s
  }, [])

  const linkPositionUpdate = useCallback(
    (obj: THREE.Object3D, { start, end }: { start: { x: number; y: number; z: number }; end: { x: number; y: number; z: number } }) => {
      const sprite = obj as THREE.Sprite
      sprite.position.set((start.x + end.x) / 2, (start.y + end.y) / 2, (start.z + end.z) / 2)
      sprite.visible = labelsRef.current
    },
    [],
  )

  useEffect(() => {
    nodeSprites.current.forEach((s) => {
      s.visible = labelsOn
    })
    for (const s of edgeSprites.current) s.visible = labelsOn
  }, [labelsOn, graphData])

  const nodePopupInfo = (node: NodeObject<Node3D>): GraphPopupInfo => ({
    kind: 'node',
    label: node.label,
    tag: node.tag,
    color: node.color,
    role: node.role,
  })
  const linkPopupInfo = (link: LinkObject<Node3D, Link3D>): GraphPopupInfo => {
    const source = typeof link.source === 'string' ? link.source : link.source.label
    const target = typeof link.target === 'string' ? link.target : link.target.label
    return { kind: 'edge', label: link.label, source, target, color: EDGE_COLOR }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <div ref={wrapRef} className="graph-surface" style={{ position: 'relative', flex: 1, minHeight: 0, background: '#eef0f4' }}>
        <ForceGraph3D<Node3D, Link3D>
        ref={fgRef}
        graphData={graphData}
        width={size?.width}
        height={size?.height}
        backgroundColor="#eef0f4"
        rendererConfig={{ preserveDrawingBuffer: true }}
        nodeId="id"
        nodeColor={(node) => (node.id === selectedVid ? SELECT_COLOR : node.color)}
        nodeVal="val"
        nodeRelSize={4}
        nodeOpacity={0.92}
        nodeResolution={14}
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={true}
        linkColor={(link) => link.color ?? EDGE_COLOR}
        linkOpacity={0.55}
        // The 3D stand-in for the 2D canvas's dotted new-link style:
        // three.js lines have no dash, so weight carries it instead.
        linkWidth={(link) => (link.isNew ? 1.8 : 0.6)}
        linkThreeObject={linkThreeObject}
        linkThreeObjectExtend={true}
        linkPositionUpdate={linkPositionUpdate}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={() => EDGE_COLOR}
        showNavInfo={false}
        enableNodeDrag={true}
        onEngineTick={holdRings}
        onNodeHover={(node) => {
          if (pinnedRef.current) return
          setPopupInfo(node ? nodePopupInfo(node) : null)
        }}
        onLinkHover={(link) => {
          if (pinnedRef.current) return
          setPopupInfo(link ? linkPopupInfo(link) : null)
        }}
        onNodeClick={(node) => {
          if (typeof node.id !== 'string') return
          onSelect(node.id)
          onToggleExpand(node.id)
          setPopupInfo(nodePopupInfo(node))
          setPinned(true)
        }}
        onLinkClick={(link) => {
          // The force graph replaces the string endpoints with node objects
          // once the simulation has run, so either form can arrive here.
          const source = typeof link.source === 'string' ? link.source : link.source?.id
          const target = typeof link.target === 'string' ? link.target : link.target?.id
          if (typeof source === 'string' && typeof target === 'string') {
            onSelectEdge?.(source, target)
          }
          setPopupInfo(linkPopupInfo(link))
          setPinned(true)
        }}
        onBackgroundClick={() => {
          onSelect(null)
          closePopup()
        }}
      />
      <button
        className={`pill-btn${labelsOn ? ' pill-btn--active' : ''}`}
        style={{ position: 'absolute', top: 12, left: 12, zIndex: 10, border: '1px solid rgba(15,23,42,0.12)', background: labelsOn ? undefined : 'rgba(255,255,255,0.85)' }}
        onClick={() => setLabelsOn((v) => !v)}
      >
        Labels {labelsOn ? 'on' : 'off'}
      </button>
      <div className="graph-3d-hint">drag to orbit · scroll to zoom</div>
      <GraphPopup info={popupInfo} pinned={pinned} onClose={closePopup} />
    </div>
      <div className="graph-legend">
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

export default GraphCanvas3D
