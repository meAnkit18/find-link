import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode } from '../../api/types'
import { computeVisibleGraph } from './graphVisibility'

const mainTags = new Set(['person'])

function node(vid: string, tags: string[]): GraphNode {
  return { vid, tags, label: vid, properties: {} }
}

function edge(src: string, dst: string): GraphEdge {
  return { src, dst, edge_type: 'HAS_PHONE', rank: 0, properties: {} }
}

describe('computeVisibleGraph', () => {
  it('shows only main nodes and main-to-main edges by default', () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('alice-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'alice-phone')]

    const { visibleNodes, visibleEdges } = computeVisibleGraph(nodes, edges, mainTags, new Set())

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob'])
    expect(visibleEdges).toHaveLength(1)
    expect(visibleEdges[0]).toMatchObject({ src: 'alice', dst: 'bob' })
  })

  it("reveals a main node's own sub nodes once that node is revealed", () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('alice-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'alice-phone')]

    const { visibleNodes, visibleEdges } = computeVisibleGraph(nodes, edges, mainTags, new Set(['alice']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'alice-phone', 'bob'])
    expect(visibleEdges).toHaveLength(2)
  })

  it("does not reveal a different main node's sub nodes", () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('bob-email', ['email'])]
    const edges = [edge('alice', 'bob'), edge('bob', 'bob-email')]

    const { visibleNodes } = computeVisibleGraph(nodes, edges, mainTags, new Set(['alice']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob'])
  })

  it('keeps a sub node shared by two main nodes visible if either is revealed', () => {
    const nodes = [node('alice', ['person']), node('bob', ['person']), node('shared-phone', ['phone'])]
    const edges = [edge('alice', 'bob'), edge('alice', 'shared-phone'), edge('bob', 'shared-phone')]

    const { visibleNodes } = computeVisibleGraph(nodes, edges, mainTags, new Set(['bob']))

    expect(visibleNodes.map((n) => n.vid).sort()).toEqual(['alice', 'bob', 'shared-phone'])
  })
})
