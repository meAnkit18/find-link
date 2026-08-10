import { useCallback, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { attributeNodeLabel } from '../components/explorer/attributeLabel'
import { EMPTY_DELTA, computeNetworkDelta, linkKey, type NetworkDelta } from './networkDelta'
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
  // What the last degree/confidence change brought in, so the canvas can
  // mark it. Held until the next filter change replaces it.
  const [addedByFilter, setAddedByFilter] = useState<NetworkDelta>(EMPTY_DELTA)
  // loadNetwork is a stable callback, so it can't close over `network` to
  // diff against — by the time a fetch resolves that binding is stale. The
  // ref always holds the projection currently on screen.
  const networkRef = useRef<PersonNetwork | null>(null)
  networkRef.current = network
  // ensureAttributes is a stable callback, so it reads the cache through a
  // ref rather than closing over a binding that goes stale.
  const attributesRef = useRef(attributes)
  attributesRef.current = attributes
  // One request per person, shared by every caller that asks while it's in
  // flight — the panel and a canvas click can want the same person's
  // attributes at the same moment, and both have to see the same answer.
  const inFlightRef = useRef<Map<string, Promise<boolean>>>(new Map())

  const reset = useCallback(() => {
    setNetwork(null)
    setAttributes(new Map())
    setExpanded(new Set())
    setError(null)
    setAddedByFilter(EMPTY_DELTA)
  }, [])

  const loadNetwork = useCallback(
    async (
      rootId: string,
      degree: number,
      opts?: { minConfidence?: number; preserveExpanded?: boolean },
    ) => {
      setLoadingNetwork(true)
      setError(null)
      try {
        const result = await api.getPersonNetwork(rootId, degree, {
          minConfidence: opts?.minConfidence,
        })
        // Diff against what was on screen before replacing it, so the
        // canvas can mark what this particular filter change pulled in.
        // Returns nothing when the root changed — see computeNetworkDelta.
        setAddedByFilter(computeNetworkDelta(networkRef.current, result))
        setNetwork(result)
        // Raising the degree is the same question asked wider, so which
        // people the user had opened still applies. A new root is a new
        // question, and nothing carries over but the attribute cache.
        if (!opts?.preserveExpanded) setExpanded(new Set())
        return result
      } catch (err) {
        setNetwork(null)
        setError((err as Error).message)
        return null
      } finally {
        setLoadingNetwork(false)
      }
    },
    [],
  )

  /** Load one person's attributes into the cache without putting them on the
   * canvas. The detail panel needs a person's documents to describe them, and
   * that has to work for someone reached by clicking a name in the panel —
   * not only for someone whose ring the user fanned out by hand.
   *
   * A no-op when they're already cached or in flight, so it's safe to call
   * from an effect on every selection change. */
  const ensureAttributes = useCallback((personId: string): Promise<boolean> => {
    if (attributesRef.current.has(personId)) return Promise.resolve(true)
    const inFlight = inFlightRef.current.get(personId)
    if (inFlight) return inFlight

    setLoadingAttributes((prev) => new Set(prev).add(personId))
    const request = api
      .getEntityAttributes(personId)
      .then((result) => {
        setAttributes((prev) => new Map(prev).set(personId, result.attributes))
        return true
      })
      .catch((err: Error) => {
        setError(err.message)
        return false
      })
      .finally(() => {
        inFlightRef.current.delete(personId)
        setLoadingAttributes((prev) => {
          const next = new Set(prev)
          next.delete(personId)
          return next
        })
      })
    inFlightRef.current.set(personId, request)
    return request
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
      if (alreadyExpanded) return

      // Expanding with nothing to show would leave a person marked open with
      // an empty ring, so a failed fetch folds them back in.
      const loaded = await ensureAttributes(personId)
      if (!loaded) {
        setExpanded((prev) => {
          const next = new Set(prev)
          next.delete(personId)
          return next
        })
      }
    },
    [expanded, ensureAttributes],
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

  /** Every attribute fetched so far, by its own vid, with everyone known to
   * hold it. The detail panel is handed an attribute id by a canvas click and
   * has to describe it without caring whose expansion first pulled it in —
   * and a document on two customer files genuinely has two holders. */
  const attributesById = useMemo(() => {
    const byId = new Map<string, { attribute: EntityAttribute; holders: string[] }>()
    for (const [personId, list] of attributes) {
      for (const attribute of list) {
        const existing = byId.get(attribute.id)
        if (existing) {
          if (!existing.holders.includes(personId)) existing.holders.push(personId)
          continue
        }
        // `shared_with` is the projection's own answer to "who else holds
        // this", so the holder list is complete even for people whose own
        // details have never been fetched.
        byId.set(attribute.id, {
          attribute,
          holders: [personId, ...attribute.shared_with.filter((id) => id !== personId)],
        })
      }
    }
    return byId
  }, [attributes])

  const canvasNodes = useMemo<GraphNode[]>(() => {
    const nodes: GraphNode[] = (network?.persons ?? []).map((person) => ({
      vid: person.id,
      tags: [PERSON_TAG],
      label: person.label,
      properties: {
        ...person.properties,
        degree: person.degree,
        is_new: addedByFilter.persons.has(person.id),
      },
    }))
    const seen = new Set<string>()
    for (const personId of expanded) {
      for (const attribute of attributes.get(personId) ?? []) {
        if (seen.has(attribute.id)) continue
        seen.add(attribute.id)
        nodes.push({
          vid: attribute.id,
          tags: [attribute.tag],
          // Canvas-only rename: a document reads as "Passport", not as its
          // number. `attribute.label` keeps the number, so the detail panel
          // and the link-reason text still show it.
          label: attributeNodeLabel(attribute),
          properties: attribute.properties,
        })
      }
    }
    return nodes
  }, [network, expanded, attributes, addedByFilter])

  const canvasEdges = useMemo<GraphEdge[]>(() => {
    const edges: GraphEdge[] = (network?.links ?? []).map((link) => ({
      src: link.source,
      dst: link.target,
      edge_type: link.label,
      rank: 0,
      // relationship_type is what the canvas prefers as an edge label,
      // via_count scales the link's width, confidence fades it, and degree
      // colors it (1st/2nd/3rd hop out from the searched person).
      properties: {
        relationship_type: link.label,
        via_count: link.via.length,
        confidence: link.confidence,
        degree: link.degree,
        is_new: addedByFilter.links.has(linkKey(link.source, link.target)),
      },
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
  }, [network, expanded, attributes, addedByFilter])

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
    attributesById,
    attributeParents,
    expanded,
    loadingNetwork,
    loadingAttributes,
    error,
    canvasNodes,
    canvasEdges,
    loadNetwork,
    ensureAttributes,
    toggleExpand,
    reset,
  }
}
