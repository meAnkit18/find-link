import { useCallback, useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  EntityAttribute,
  GraphEdge,
  GraphNode,
  PersonLink,
  PersonNetwork,
} from '../api/types'

export const PERSON_TAG = 'person'

/** Investigation's data layer: the projected person network, plus which
 * people have had their own details fanned out.
 *
 * Attributes are fetched once per person and kept even when collapsed —
 * re-expanding is then instant, with no spinner and no second round trip.
 */
export function usePersonNetworkState() {
  const [network, setNetwork] = useState<PersonNetwork | null>(null)
  const [attributes, setAttributes] = useState<Map<string, EntityAttribute[]>>(new Map())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [loadingNetwork, setLoadingNetwork] = useState(false)
  const [loadingAttributes, setLoadingAttributes] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  const reset = useCallback(() => {
    setNetwork(null)
    setAttributes(new Map())
    setExpanded(new Set())
    setError(null)
  }, [])

  const loadNetwork = useCallback(async (rootId: string, degree: number) => {
    setLoadingNetwork(true)
    setError(null)
    try {
      const result = await api.getPersonNetwork(rootId, degree)
      setNetwork(result)
      // A new network is a new question — nothing carries over except the
      // attribute cache, which is keyed by person and still valid.
      setExpanded(new Set())
      return result
    } catch (err) {
      setNetwork(null)
      setError((err as Error).message)
      return null
    } finally {
      setLoadingNetwork(false)
    }
  }, [])

  const toggleExpand = useCallback(
    async (personId: string) => {
      const alreadyExpanded = expanded.has(personId)
      setExpanded((prev) => {
        const next = new Set(prev)
        if (alreadyExpanded) next.delete(personId)
        else next.add(personId)
        return next
      })
      if (alreadyExpanded || attributes.has(personId)) return

      setLoadingAttributes((prev) => new Set(prev).add(personId))
      try {
        const result = await api.getEntityAttributes(personId)
        setAttributes((prev) => new Map(prev).set(personId, result.attributes))
      } catch (err) {
        setError((err as Error).message)
        setExpanded((prev) => {
          const next = new Set(prev)
          next.delete(personId)
          return next
        })
      } finally {
        setLoadingAttributes((prev) => {
          const next = new Set(prev)
          next.delete(personId)
          return next
        })
      }
    },
    [expanded, attributes],
  )

  /** Attribute id -> the expanded people holding it. An attribute two
   * expanded people share has two parents, which is what puts it between
   * them rather than in either one's ring. */
  const attributeParents = useMemo(() => {
    const parents = new Map<string, string[]>()
    for (const personId of expanded) {
      for (const attribute of attributes.get(personId) ?? []) {
        const holders = parents.get(attribute.id)
        if (holders) holders.push(personId)
        else parents.set(attribute.id, [personId])
      }
    }
    return parents
  }, [expanded, attributes])

  const canvasNodes = useMemo<GraphNode[]>(() => {
    const nodes: GraphNode[] = (network?.persons ?? []).map((person) => ({
      vid: person.id,
      tags: [PERSON_TAG],
      label: person.label,
      properties: { ...person.properties, degree: person.degree },
    }))
    const seen = new Set<string>()
    for (const personId of expanded) {
      for (const attribute of attributes.get(personId) ?? []) {
        if (seen.has(attribute.id)) continue
        seen.add(attribute.id)
        nodes.push({
          vid: attribute.id,
          tags: [attribute.tag],
          label: attribute.label,
          properties: attribute.properties,
        })
      }
    }
    return nodes
  }, [network, expanded, attributes])

  const canvasEdges = useMemo<GraphEdge[]>(() => {
    const edges: GraphEdge[] = (network?.links ?? []).map((link) => ({
      src: link.source,
      dst: link.target,
      edge_type: link.label,
      rank: 0,
      // relationship_type is what the canvas prefers as an edge label, and
      // via_count is what scales the link's width.
      properties: { relationship_type: link.label, via_count: link.via.length },
    }))
    for (const personId of expanded) {
      for (const attribute of attributes.get(personId) ?? []) {
        edges.push({
          src: personId,
          dst: attribute.id,
          edge_type: attribute.edge_type || 'has',
          rank: 0,
          properties: {},
        })
      }
    }
    return edges
  }, [network, expanded, attributes])

  const linksByPerson = useMemo(() => {
    const byPerson = new Map<string, PersonLink[]>()
    for (const link of network?.links ?? []) {
      for (const end of [link.source, link.target]) {
        const existing = byPerson.get(end)
        if (existing) existing.push(link)
        else byPerson.set(end, [link])
      }
    }
    return byPerson
  }, [network])

  const personsById = useMemo(
    () => new Map((network?.persons ?? []).map((person) => [person.id, person])),
    [network],
  )

  return {
    network,
    personsById,
    linksByPerson,
    attributes,
    attributeParents,
    expanded,
    loadingNetwork,
    loadingAttributes,
    error,
    canvasNodes,
    canvasEdges,
    loadNetwork,
    toggleExpand,
    reset,
  }
}
