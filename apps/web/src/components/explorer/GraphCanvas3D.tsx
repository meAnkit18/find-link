import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react'
import ForceGraph3D, { type ForceGraphMethods } from 'react-force-graph-3d'
import type { GraphEdge, GraphNode } from '../../api/types'
import { colorForTag, edgeLabel, roleForNode } from './graphStyle'
import type { GraphCanvasHandle } from './GraphCanvas'

interface Node3D {
  id: string
  label: string
  color: string
  val: number
}

interface Link3D {
  source: string
  target: string
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

const GraphCanvas3D = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas3D(
  { nodes, edges, selectedVid, mainTags, onSelect, onToggleExpand },
  ref,
) {
  const fgRef = useRef<ForceGraphMethods<Node3D, Link3D>>()
  const selectedVidRef = useRef(selectedVid)
  selectedVidRef.current = selectedVid

  const graphData = useMemo(() => {
    const graphNodes: Node3D[] = nodes.map((n) => ({
      id: n.vid,
      label: n.label,
      color: colorForTag(n.tags[0] ?? 'entity'),
      val: roleForNode(n, mainTags) === 'main' ? 6 : 2,
    }))
    const graphLinks: Link3D[] = edges.map((e) => ({
      source: e.src,
      target: e.dst,
      label: edgeLabel(e),
    }))
    return { nodes: graphNodes, links: graphLinks }
  }, [nodes, edges, mainTags])

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

  return (
    <ForceGraph3D<Node3D, Link3D>
      ref={fgRef}
      graphData={graphData}
      backgroundColor="#11141a"
      rendererConfig={{ preserveDrawingBuffer: true }}
      nodeId="id"
      nodeLabel="label"
      nodeColor={(node) => (node.id === selectedVid ? '#ffffff' : node.color)}
      nodeVal="val"
      nodeRelSize={4}
      linkColor={() => '#5b6472'}
      linkLabel="label"
      linkDirectionalArrowLength={3}
      linkDirectionalArrowRelPos={1}
      onNodeClick={(node) => {
        if (typeof node.id !== 'string') return
        onSelect(node.id)
        onToggleExpand(node.id)
      }}
      onBackgroundClick={() => onSelect(null)}
    />
  )
})

export default GraphCanvas3D
