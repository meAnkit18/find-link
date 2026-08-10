import type { PersonNetwork } from '../api/types'

/** Which people and links the most recent projection added that the
 * previous one didn't have. */
export interface NetworkDelta {
  persons: Set<string>
  links: Set<string>
}

export const EMPTY_DELTA: NetworkDelta = { persons: new Set(), links: new Set() }

/** Identity for a person link. Deliberately the unordered pair rather than
 * the canvas's `edgeId`: that folds in the edge label, which is derived
 * from the link's `via` list and legitimately changes when a wider degree
 * finds another reason for the same connection. Keying on the label would
 * report an existing link as brand new the moment its explanation grew. */
export function linkKey(source: string, target: string): string {
  return source < target ? `${source}|${target}` : `${target}|${source}`
}

/** Diff two projections of the same person network.
 *
 * Returns nothing when there is no previous network, or when the root
 * changed — that's a new search rather than a filter change, and marking
 * every node as "new" would say nothing at all.
 */
export function computeNetworkDelta(
  previous: PersonNetwork | null,
  next: PersonNetwork,
): NetworkDelta {
  if (!previous || previous.root_id !== next.root_id) return EMPTY_DELTA

  const knownPersons = new Set(previous.persons.map((person) => person.id))
  const knownLinks = new Set(previous.links.map((link) => linkKey(link.source, link.target)))

  return {
    persons: new Set(
      next.persons.filter((person) => !knownPersons.has(person.id)).map((person) => person.id),
    ),
    links: new Set(
      next.links
        .map((link) => linkKey(link.source, link.target))
        .filter((key) => !knownLinks.has(key)),
    ),
  }
}
