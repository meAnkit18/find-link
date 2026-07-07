import { useEffect, useRef } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
// @ts-expect-error - cytoscape-fcose has no bundled types
import fcose from 'cytoscape-fcose'
import type { GraphEdge, GraphNode } from '../../api/types'

cytoscape.use(fcose)

const TAG_PALETTE = [
  '#5b8def',
  '#e5a95b',
  '#7fd1ae',
  '#d17fd1',
  '#d15b5b',
  '#5bc8d1',
]

function colorForTag(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) >>> 0
  return TAG_PALETTE[hash % TAG_PALETTE.length]
}

function edgeId(edge: GraphEdge): string {
  return `${edge.src}->${edge.dst}@${edge.edge_type}@${edge.rank}`
}

const STYLE: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': (ele: cytoscape.NodeSingular) => colorForTag(ele.data('tag')),
      label: 'data(label)',
      color: '#e6e8ec',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 6,
      width: 26,
      height: 26,
      'border-width': 2,
      'border-color': '#0f1115',
      'text-outline-width': 2,
      'text-outline-color': '#0f1115',
    },
  },
  {
    selector: 'node:selected',
    style: { 'border-color': '#5b8def', 'border-width': 3 },
  },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#3a3f4b',
      'target-arrow-color': '#3a3f4b',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      label: 'data(edgeType)',
      'font-size': 8,
      color: '#9aa1ad',
      'text-background-color': '#0f1115',
      'text-background-opacity': 0.8,
      'text-background-padding': '2px',
    },
  },
]

interface Props {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedVid: string | null
  onSelect: (vid: string | null) => void
  onExpand: (vid: string) => void
}

export default function GraphCanvas({ nodes, edges, selectedVid, onSelect, onExpand }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const onSelectRef = useRef(onSelect)
  const onExpandRef = useRef(onExpand)
  onSelectRef.current = onSelect
  onExpandRef.current = onExpand

  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      style: STYLE,
      wheelSensitivity: 0.2,
    })
    cyRef.current = cy

    cy.on('tap', 'node', (evt) => onSelectRef.current(evt.target.id()))
    cy.on('tap', (evt) => {
      if (evt.target === cy) onSelectRef.current(null)
    })
    cy.on('dbltap', 'node', (evt) => onExpandRef.current(evt.target.id()))

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const hadNodesBefore = cy.nodes().length > 0
    const desiredNodeIds = new Set(nodes.map((n) => n.vid))
    const desiredEdgeIds = new Set(edges.map(edgeId))

    cy.edges().forEach((ele) => {
      if (!desiredEdgeIds.has(ele.id())) ele.remove()
    })
    cy.nodes().forEach((ele) => {
      if (!desiredNodeIds.has(ele.id())) ele.remove()
    })

    const newNodeEles: ElementDefinition[] = nodes
      .filter((n) => cy.getElementById(n.vid).empty())
      .map((n) => ({ data: { id: n.vid, label: n.label, tag: n.tags[0] ?? 'entity' } }))

    const newEdgeEles: ElementDefinition[] = edges
      .filter((e) => cy.getElementById(edgeId(e)).empty())
      .map((e) => ({
        data: { id: edgeId(e), source: e.src, target: e.dst, edgeType: e.edge_type },
      }))

    const added = cy.add([...newNodeEles, ...newEdgeEles])

    if (added.length > 0) {
      // fcose's options (animate/randomize/nodeRepulsion/...) aren't part of
      // @types/cytoscape's built-in layout typings, hence the cast.
      const fcoseOptions = {
        name: 'fcose',
        animate: true,
        randomize: !hadNodesBefore,
        fit: false,
        nodeRepulsion: 8000,
        idealEdgeLength: 90,
      } as unknown as cytoscape.LayoutOptions
      const layout = cy.layout(fcoseOptions)
      if (!hadNodesBefore) {
        layout.one('layoutstop', () => cy.fit(undefined, 40))
      }
      layout.run()
    }
  }, [nodes, edges])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes().unselect()
    if (selectedVid) cy.getElementById(selectedVid).select()
  }, [selectedVid])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
