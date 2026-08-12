import { describe, expect, it } from 'vitest'
import type { PersonLink, PersonNode } from '../../../api/types'
import { edgeConfidence, edgeDegree, edgeLabel, edgeWeight, nodeDegree } from '../graphStyle'
import { linkToEdge, pathToElements, personToNode } from './connectionGraphElements'

function person(overrides: Partial<PersonNode> = {}): PersonNode {
  return {
    id: 'p:1',
    label: 'A. Kumar',
    degree: 0,
    entity_type: 'person',
    properties: { country: 'NG' },
    ...overrides,
  } as PersonNode
}

function link(overrides: Partial<PersonLink> = {}): PersonLink {
  return {
    source: 'p:1',
    target: 'p:2',
    degree: 1,
    label: 'shared phone',
    confidence: 0.82,
    via: [{ kind: 'direct', edge_types: ['RELATED_TO'], label: 'shared phone' }],
    ...overrides,
  } as PersonLink
}

describe('personToNode', () => {
  it('carries the projection degree where graphStyle reads it', () => {
    expect(nodeDegree(personToNode(person({ degree: 2 })))).toBe(2)
  })

  it('keeps the person properties alongside the degree', () => {
    expect(personToNode(person()).properties.country).toBe('NG')
  })

  it('falls back to the person tag when the entity type is blank', () => {
    expect(personToNode(person({ entity_type: '' })).tags).toEqual(['person'])
  })
})

describe('linkToEdge', () => {
  it('labels the edge with the projection summary, not the raw type', () => {
    expect(edgeLabel(linkToEdge(link({ label: 'shared address' })))).toBe('shared address')
  })

  it('carries degree, confidence and via count where graphStyle reads them', () => {
    const edge = linkToEdge(
      link({
        degree: 3,
        confidence: 0.4,
        via: [
          { kind: 'direct', edge_types: ['A'], label: 'x' },
          { kind: 'direct', edge_types: ['B'], label: 'y' },
        ] as PersonLink['via'],
      }),
    )
    expect(edgeDegree(edge)).toBe(3)
    expect(edgeConfidence(edge)).toBeCloseTo(0.4)
    expect(edgeWeight(edge)).toBe(2)
  })

  it('gives a via-less link weight 1 rather than 0', () => {
    expect(edgeWeight(linkToEdge(link({ via: [] })))).toBe(1)
  })
})

describe('pathToElements', () => {
  it('maps every person and link, preserving path order', () => {
    const { nodes, edges } = pathToElements(
      [person({ id: 'p:1' }), person({ id: 'p:2', degree: 1 })],
      [link()],
    )
    expect(nodes.map((n) => n.vid)).toEqual(['p:1', 'p:2'])
    expect(edges).toHaveLength(1)
    expect(edges[0].src).toBe('p:1')
    expect(edges[0].dst).toBe('p:2')
  })
})
