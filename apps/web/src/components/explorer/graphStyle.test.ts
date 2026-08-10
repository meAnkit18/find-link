import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode } from '../../api/types'
import { DEGREE_PALETTE, colorForDegree, edgeDegree, nodeDegree } from './graphStyle'

function node(properties: Record<string, unknown>): GraphNode {
  return { vid: 'p1', tags: ['person'], label: 'Omar', properties }
}

function edge(properties: Record<string, unknown>): GraphEdge {
  return { src: 'p1', dst: 'p2', edge_type: 'shared phone', rank: 0, properties }
}

describe('colorForDegree', () => {
  it('gives each of the first three degrees its own color', () => {
    const colors = [colorForDegree(1), colorForDegree(2), colorForDegree(3)]
    expect(colors).toEqual(DEGREE_PALETTE)
    expect(new Set(colors).size).toBe(3)
  })

  it('returns null for the root, so it keeps its tag color', () => {
    expect(colorForDegree(0)).toBeNull()
  })

  it('returns null when there is no degree at all', () => {
    expect(colorForDegree(null)).toBeNull()
    expect(colorForDegree(Number.NaN)).toBeNull()
  })

  it('clamps past the end of the palette instead of wrapping', () => {
    // Wrapping would repaint the most distant people in 1st-degree violet.
    const last = DEGREE_PALETTE[DEGREE_PALETTE.length - 1]
    expect(colorForDegree(4)).toBe(last)
    expect(colorForDegree(9)).toBe(last)
    expect(colorForDegree(4)).not.toBe(colorForDegree(1))
  })
})

describe('nodeDegree', () => {
  it('reads the degree the person projection stamps on', () => {
    expect(nodeDegree(node({ degree: 2 }))).toBe(2)
    expect(nodeDegree(node({ degree: 0 }))).toBe(0)
  })

  it('is null for a node carrying no degree', () => {
    expect(nodeDegree(node({}))).toBeNull()
    expect(nodeDegree(node({ degree: 'unknown' }))).toBeNull()
  })
})

describe('edgeDegree', () => {
  it('reads the degree a link was found at', () => {
    expect(edgeDegree(edge({ degree: 3 }))).toBe(3)
  })

  it('is null for an attribute spoke, which has no degree', () => {
    expect(edgeDegree(edge({}))).toBeNull()
  })
})
