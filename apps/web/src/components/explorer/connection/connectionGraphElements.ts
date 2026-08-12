import type { GraphEdge, GraphNode, PersonLink, PersonNode } from '../../../api/types'
import { PERSON_TAG } from '../../../hooks/usePersonNetworkState'

// Turns a `find_connection` path into the plain GraphNode/GraphEdge shape
// the shared cytoscape canvas already draws, so Verify connection reuses
// Explore's canvas rather than owning a second renderer.
//
// The property names here are not arbitrary: `graphStyle.ts` reads
// `properties.degree`, `properties.confidence`, `properties.via_count` and
// `properties.relationship_type` off these objects to pick a node's degree
// colour, an edge's weight and its label. Writing the projection's values
// into those keys is what makes a hop on this canvas look like the same
// hop on Explore's.

/** One person on the path. `degree` carries through to `nodeDegree`, so the
 * violet/teal/crimson degree ramp means the same thing here as on Explore. */
export function personToNode(person: PersonNode): GraphNode {
  return {
    vid: person.id,
    tags: [person.entity_type || PERSON_TAG],
    label: person.label,
    properties: { ...person.properties, degree: person.degree },
  }
}

/** One hop. The projection's human-readable summary ("shared phone") is
 * written to `relationship_type` because `edgeLabel` prefers that over the
 * raw edge type — the raw type is a code, and the whole point of this view
 * is that a hop states its own reason.
 *
 * `rank` is 0 rather than an index: `edgeId` keys on src/dst/type/rank, and
 * a path visits each pair once, so 0 is already unique. */
export function linkToEdge(link: PersonLink): GraphEdge {
  return {
    src: link.source,
    dst: link.target,
    edge_type: link.label,
    rank: 0,
    properties: {
      degree: link.degree,
      confidence: link.confidence,
      via_count: link.via.length,
      relationship_type: link.label,
    },
  }
}

export function pathToElements(persons: PersonNode[], links: PersonLink[]): {
  nodes: GraphNode[]
  edges: GraphEdge[]
} {
  return { nodes: persons.map(personToNode), edges: links.map(linkToEdge) }
}
