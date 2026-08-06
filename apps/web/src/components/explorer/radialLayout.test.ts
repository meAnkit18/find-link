import { describe, expect, it } from 'vitest'
import { computeRadialPositions, type Position, type RadialChild } from './radialLayout'

function child(id: string, parentIds: string[], sortKey = id): RadialChild {
  return { id, parentIds, sortKey }
}

function distance(a: Position, b: Position): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

const origin: Position = { x: 0, y: 0 }

describe('computeRadialPositions', () => {
  it('places a single parent’s children on a circle around it', () => {
    const parents = new Map([['alice', { x: 100, y: 50 }]])
    const children = [child('phone', ['alice']), child('email', ['alice']), child('addr', ['alice'])]

    const positions = computeRadialPositions(parents, children)

    expect(positions.size).toBe(3)
    const radii = [...positions.values()].map((p) => distance(p, { x: 100, y: 50 }))
    for (const r of radii) expect(r).toBeCloseTo(radii[0], 6)
  })

  it('spaces children evenly around the ring', () => {
    const parents = new Map([['alice', origin]])
    const children = [child('a', ['alice']), child('b', ['alice']), child('c', ['alice']), child('d', ['alice'])]

    const positions = computeRadialPositions(parents, children)
    const angles = ['a', 'b', 'c', 'd'].map((id) => {
      const p = positions.get(id)!
      return Math.atan2(p.y, p.x)
    })
    const gaps = angles.slice(1).map((angle, i) => {
      const gap = angle - angles[i]
      return gap < 0 ? gap + 2 * Math.PI : gap
    })
    for (const gap of gaps) expect(gap).toBeCloseTo(Math.PI / 2, 6)
  })

  it('grows the ring so a crowded person’s details do not overlap', () => {
    const parents = new Map([['alice', origin]])
    const few = computeRadialPositions(
      parents,
      Array.from({ length: 3 }, (_, i) => child(`f${i}`, ['alice'])),
    )
    const many = computeRadialPositions(
      parents,
      Array.from({ length: 30 }, (_, i) => child(`m${i}`, ['alice'])),
    )

    expect(distance(many.get('m0')!, origin)).toBeGreaterThan(distance(few.get('f0')!, origin))
  })

  it('keeps neighbouring children at least the spacing apart in a big ring', () => {
    const parents = new Map([['alice', origin]])
    const children = Array.from({ length: 24 }, (_, i) => child(`c${String(i).padStart(2, '0')}`, ['alice']))

    const positions = computeRadialPositions(parents, children, { spacing: 40 })
    const ordered = children.map((c) => positions.get(c.id)!)
    for (let i = 1; i < ordered.length; i++) {
      expect(distance(ordered[i], ordered[i - 1])).toBeGreaterThan(30)
    }
  })

  it('is stable across repeated calls', () => {
    const parents = new Map([['alice', { x: 12, y: -4 }]])
    const children = [child('phone', ['alice']), child('email', ['alice'])]

    const first = computeRadialPositions(parents, children)
    const second = computeRadialPositions(parents, [...children].reverse())

    expect([...second.entries()].sort()).toEqual([...first.entries()].sort())
  })

  it('gives two people different starting angles so their rings interleave less', () => {
    const parents = new Map([
      ['alice', origin],
      ['bob', { x: 300, y: 0 }],
    ])
    const positions = computeRadialPositions(parents, [
      child('a1', ['alice']),
      child('b1', ['bob']),
    ])

    const alice = positions.get('a1')!
    const bob = positions.get('b1')!
    const aliceAngle = Math.atan2(alice.y - 0, alice.x - 0)
    const bobAngle = Math.atan2(bob.y - 0, bob.x - 300)
    expect(aliceAngle).not.toBeCloseTo(bobAngle, 3)
  })

  it('puts an attribute shared by two expanded people between them', () => {
    const parents = new Map([
      ['alice', { x: 0, y: 0 }],
      ['bob', { x: 200, y: 0 }],
    ])

    const positions = computeRadialPositions(parents, [child('phone', ['alice', 'bob'])])

    expect(positions.get('phone')).toEqual({ x: 100, y: 0 })
  })

  it('fans several shared attributes apart instead of stacking them', () => {
    const parents = new Map([
      ['alice', { x: 0, y: 0 }],
      ['bob', { x: 200, y: 0 }],
    ])

    const positions = computeRadialPositions(
      parents,
      [child('phone', ['alice', 'bob']), child('email', ['alice', 'bob'])],
      { spacing: 40 },
    )

    const a = positions.get('phone')!
    const b = positions.get('email')!
    expect(a).not.toEqual(b)
    expect(distance(a, b)).toBeCloseTo(40, 6)
    // both still on the perpendicular through the midpoint
    expect(a.x).toBeCloseTo(100, 6)
    expect(b.x).toBeCloseTo(100, 6)
  })

  it('treats a shared attribute as an ordinary child when only one parent is expanded', () => {
    const parents = new Map([['alice', origin]])

    const positions = computeRadialPositions(parents, [child('phone', ['alice', 'bob'])])

    expect(distance(positions.get('phone')!, origin)).toBeGreaterThan(0)
  })

  it('omits children whose parents are all collapsed', () => {
    const parents = new Map([['alice', origin]])

    const positions = computeRadialPositions(parents, [child('phone', ['bob'])])

    expect(positions.size).toBe(0)
  })

  it('handles two people standing on the same spot', () => {
    const parents = new Map([
      ['alice', origin],
      ['bob', origin],
    ])

    const positions = computeRadialPositions(parents, [child('phone', ['alice', 'bob'])])

    expect(positions.get('phone')).toEqual({ x: 0, y: 0 })
  })
})
