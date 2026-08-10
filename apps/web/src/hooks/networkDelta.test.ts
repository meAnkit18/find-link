import { describe, expect, it } from 'vitest'
import type { PersonLink, PersonNetwork, PersonNode } from '../api/types'
import { computeNetworkDelta, linkKey } from './networkDelta'

function person(id: string, degree: number): PersonNode {
  return { id, label: id, degree, entity_type: 'Person', properties: {} }
}

function link(source: string, target: string, degree: number, label = 'shared phone'): PersonLink {
  return { source, target, degree, label, confidence: 0.8, via: [] }
}

function network(rootId: string, persons: PersonNode[], links: PersonLink[]): PersonNetwork {
  return {
    root_id: rootId,
    degree: 2,
    min_confidence: 0,
    persons,
    links,
    truncated: false,
    suppressed_hubs: [],
    connectors: { direct: [], shared: [] },
  }
}

describe('linkKey', () => {
  it('is the same whichever way round the link is stored', () => {
    expect(linkKey('a', 'b')).toBe(linkKey('b', 'a'))
  })

  it('separates different pairs', () => {
    expect(linkKey('a', 'b')).not.toBe(linkKey('a', 'c'))
  })
})

describe('computeNetworkDelta', () => {
  const before = network('root', [person('root', 0), person('a', 1)], [link('root', 'a', 1)])

  it('reports what raising the degree added', () => {
    const after = network(
      'root',
      [person('root', 0), person('a', 1), person('b', 2)],
      [link('root', 'a', 1), link('a', 'b', 2)],
    )

    const delta = computeNetworkDelta(before, after)

    expect([...delta.persons]).toEqual(['b'])
    expect([...delta.links]).toEqual([linkKey('a', 'b')])
  })

  it('does not report anything already on screen', () => {
    const delta = computeNetworkDelta(before, before)
    expect(delta.persons.size).toBe(0)
    expect(delta.links.size).toBe(0)
  })

  it('marks nothing on a brand new search', () => {
    // A different root is a new question, not a widened one — marking every
    // node as new would carry no information.
    const other = network('someone-else', [person('someone-else', 0), person('z', 1)], [])
    const delta = computeNetworkDelta(before, other)
    expect(delta.persons.size).toBe(0)
    expect(delta.links.size).toBe(0)
  })

  it('marks nothing when there was no previous network', () => {
    const delta = computeNetworkDelta(null, before)
    expect(delta.persons.size).toBe(0)
    expect(delta.links.size).toBe(0)
  })

  it('does not call an existing link new just because its label grew', () => {
    // A wider degree can find a second reason for a connection, which
    // rewrites the link's label. The pair is what makes it the same link.
    const relabelled = network(
      'root',
      [person('root', 0), person('a', 1)],
      [link('root', 'a', 1, 'shared phone + shared address')],
    )

    expect(computeNetworkDelta(before, relabelled).links.size).toBe(0)
  })

  it('treats a link stored in the opposite direction as the same link', () => {
    const flipped = network('root', [person('root', 0), person('a', 1)], [link('a', 'root', 1)])
    expect(computeNetworkDelta(before, flipped).links.size).toBe(0)
  })
})
