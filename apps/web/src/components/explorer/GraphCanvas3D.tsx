import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import ForceGraph3D, { type ForceGraphMethods, type NodeObject, type LinkObject } from 'react-force-graph-3d'
import * as THREE from 'three'
import type { GraphEdge, GraphNode } from '../../api/types'
import { EDGE_COLOR, SELECT_COLOR, colorForTag, edgeLabel, roleForNode, type NodeRole } from './graphStyle'
import type { GraphCanvasHandle } from './GraphCanvas'
import GraphPopup, { type GraphPopupInfo } from './GraphPopup'

interface Node3D {
  id: string
  label: string
  tag: string
  role: NodeRole
  color: string
  val: number
}

interface Link3D {
  // react-force-graph mutates these from ids into resolved node objects
  // once the simulation has run, hence the union.
  source: string | Node3D
  target: string | Node3D
  label: string
}

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  mainTags: Set<string>
  onSelect: (vid: string | null) => void
  onToggleExpand: (vid: string) => void
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

function makeTextTexture(text: string, ink: string): { tex: THREE.CanvasTexture; aspect: number } {
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
  ctx.fillStyle = 'rgba(6,9,16,0.55)'
  roundRectPath(ctx, 0.75, 0.75, w - 1.5, h - 1.5, h / 2)
  ctx.fill()
  ctx.lineWidth = 1
  ctx.strokeStyle = 'rgba(255,255,255,0.08)'
  roundRectPath(ctx, 0.75, 0.75, w - 1.5, h - 1.5, h / 2)
  ctx.stroke()
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
  { nodes, edges, selectedVid, mainTags, onSelect, onToggleExpand },
  ref,
) {
  const fgRef = useRef<ForceGraphMethods<Node3D, Link3D>>()
  const wrapRef = useRef<HTMLDivElement>(null)
  const selectedVidRef = useRef(selectedVid)
  selectedVidRef.current = selectedVid

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
      return { id: n.vid, label: n.label, tag, role, color: colorForTag(tag), val: role === 'main' ? 6 : 2 }
    })
    const graphLinks: Link3D[] = edges.map((e) => ({ source: e.src, target: e.dst, label: edgeLabel(e) }))
    return { nodes: graphNodes, links: graphLinks }
  }, [nodes, edges, mainTags])

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

  // A soft global bloom so every node/edge gets a gentle glow, matching
  // kindred's graph-3d.tsx (much subtler than the halo below).
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    let cancelled = false
    import('three/examples/jsm/postprocessing/UnrealBloomPass.js')
      .then(({ UnrealBloomPass }) => {
        if (cancelled) return
        try {
          const bloom = new UnrealBloomPass(undefined as unknown as THREE.Vector2, 0.38, 0.5, 0.18)
          fg.postProcessingComposer().addPass(bloom)
        } catch {
          // best-effort — a missing bloom pass shouldn't break the graph
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

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

    const ink = node.id === selectedVidRef.current ? SELECT_COLOR : node.color
    const { tex, aspect } = makeTextTexture(node.label, ink)
    textures.current.push(tex)
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.95 }))
    const wh = node.role === 'main' ? 4.2 : 3.2
    const radius = Math.cbrt(Math.max(0.1, node.val ?? 2)) * 4
    label.scale.set(wh * aspect, wh, 1)
    label.position.set(0, radius + wh * 0.5 + 1.8, 0)
    label.raycast = () => {}
    label.visible = labelsRef.current
    group.add(label)
    nodeSprites.current.set(node.id, label)

    if (node.role === 'main' || node.id === selectedVidRef.current) {
      const color = node.id === selectedVidRef.current ? SELECT_COLOR : node.color
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
    const { tex, aspect } = makeTextTexture(link.label, EDGE_COLOR)
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
    <div ref={wrapRef} style={{ position: 'relative', width: '100%', height: '100%', background: '#05070d' }}>
      <ForceGraph3D<Node3D, Link3D>
        ref={fgRef}
        graphData={graphData}
        backgroundColor="#05070d"
        rendererConfig={{ preserveDrawingBuffer: true }}
        nodeId="id"
        nodeColor={(node) => (node.id === selectedVid ? '#ffffff' : node.color)}
        nodeVal="val"
        nodeRelSize={4}
        nodeOpacity={0.92}
        nodeResolution={14}
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={true}
        linkColor={() => EDGE_COLOR}
        linkOpacity={0.55}
        linkWidth={0.6}
        linkThreeObject={linkThreeObject}
        linkThreeObjectExtend={true}
        linkPositionUpdate={linkPositionUpdate}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalArrowColor={() => EDGE_COLOR}
        showNavInfo={false}
        enableNodeDrag={true}
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
        style={{ position: 'absolute', top: 12, left: 12, zIndex: 10, border: '1px solid rgba(255,255,255,0.1)', background: labelsOn ? undefined : 'rgba(255,255,255,0.06)' }}
        onClick={() => setLabelsOn((v) => !v)}
      >
        Labels {labelsOn ? 'on' : 'off'}
      </button>
      <div className="graph-3d-hint">drag to orbit · scroll to zoom</div>
      <GraphPopup info={popupInfo} pinned={pinned} onClose={closePopup} />
    </div>
  )
})

export default GraphCanvas3D
