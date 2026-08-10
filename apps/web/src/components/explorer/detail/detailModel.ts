// Everything the Investigation detail panel needs to *decide* — what a link
// reason says, which document fields matched whom, how a score reads in
// words. Kept apart from the views so it can be tested without a DOM, the
// same way graphStyle/attributeLabel/radialLayout are.

import type { EntityAttribute, PersonLink, PersonLinkVia, PersonNode } from '../../../api/types'
import { humanizeLabel } from '../../common/format'
import { humanizeWords } from '../attributeLabel'

/** Everything the detail views read. Assembled once by the page and passed
 * down whole, so a view never reaches back into the page's state and the
 * views stay swappable. */
export interface DetailData {
  personsById: Map<string, PersonNode>
  /** Every projected link, and the same links indexed by each endpoint. */
  links: PersonLink[]
  linksByPerson: Map<string, PersonLink[]>
  attributes: Map<string, EntityAttribute[]>
  attributesById: Map<string, { attribute: EntityAttribute; holders: string[] }>
  expanded: Set<string>
  loadingAttributes: Set<string>
  /** Output of `buildFieldMatchIndex` over `links`. */
  fieldMatches: Map<string, Set<string>>
  rootLabel: string
}

/** Everything the detail views can do. All of it already existed on the
 * Investigation page; this is the contract, not new behavior. */
export interface DetailActions {
  select: (selection: Selection | null) => void
  /** Select a vid without the caller having to know whether it's a person or
   * an attribute. */
  openVid: (vid: string) => void
  /** A vid's display label, or null when nothing on screen knows it. */
  labelFor: (vid: string) => string | null
  toggleExpand: (personId: string) => void
  fetchRisk: (personId: string) => void
}

/** What the right panel is currently describing.
 *
 * A projected link has no vid of its own, so it is identified by its two
 * endpoints — the projection emits at most one link per pair of people, so
 * the pair is a key. */
export type Selection =
  | { kind: 'person'; id: string }
  | { kind: 'attribute'; id: string }
  | { kind: 'link'; source: string; target: string }

/** A stable string per selection, used as the React `key` on the detail
 * view so that switching nodes resets the view's own state (which tab is
 * open) instead of carrying a stale tab over to a different entity. */
export function selectionKey(selection: Selection | null): string {
  if (!selection) return 'none'
  if (selection.kind === 'link') return `link:${selection.source}|${selection.target}`
  return `${selection.kind}:${selection.id}`
}

// ---------------------------------------------------------------- confidence

export type ConfidenceTone = 'strong' | 'moderate' | 'weak'

/** Which band a 0-1 link score falls in. The panel shows the band next to
 * the number because the number alone doesn't travel: scores are noisy-OR'd
 * across independent reasons, so "0.31" only means something relative to
 * the thresholds an investigator would actually act on. */
export function confidenceTone(confidence: number): ConfidenceTone {
  if (confidence >= 0.7) return 'strong'
  if (confidence >= 0.35) return 'moderate'
  return 'weak'
}

export function confidenceLabel(confidence: number): string {
  switch (confidenceTone(confidence)) {
    case 'strong':
      return 'Strong'
    case 'moderate':
      return 'Moderate'
    default:
      return 'Weak'
  }
}

/** Colour for a risk level. Deliberately *not* the confidence palette: a
 * high confidence is good news and a high risk is bad, so sharing one scale
 * would paint a HIGH-risk person in the same green as a well-evidenced
 * link. */
export function riskColor(level: string): string {
  switch (level) {
    case 'high':
      return '#c23b32'
    case 'medium':
      return '#b5720a'
    default:
      return '#1e8a5f'
  }
}

// ------------------------------------------------------------- link reasons

/** One `via` entry, flattened into the fields a card renders.
 *
 * `connector` is only set when the reason hangs off a vertex the canvas can
 * actually show. Notably a `shared_field` reason does *not* set it: its
 * connector is a field-value index vertex, which is deliberately kept off
 * the graph (it would link everyone who shares a value to everyone else).
 * Its `documentIds` are the openable nodes for that reason instead. */
export interface ReasonDescriptor {
  kind: PersonLinkVia['kind']
  /** What sort of evidence this is — the card's heading. */
  heading: string
  /** One sentence stating the reason in full. */
  detail: string
  connector?: { id: string; tag: string; label: string }
  /** The second organisation in a `linked_organisation` reason. */
  linked?: { id: string; tag: string; label: string }
  /** Which field(s) agreed, humanized, for a field match. */
  fields?: string[]
  /** The same field keys as stored, for looking the value back up. */
  fieldKeys?: string[]
  /** The matched value as it is indexed — normalised, so not for display. */
  matchedValue?: string
  /** This reason's own score, when it carries one. */
  confidence?: number
  /** The documents that stated the matched value, so a reason stays
   * auditable back to its source. */
  documentIds?: string[]
}

/** @param displayValue how a field match's value should read, when a caller
 * has recovered it from the citing document. Defaults to the projection's
 * own label, which is the normalised index key. */
export function describeVia(via: PersonLinkVia, displayValue?: string): ReasonDescriptor {
  switch (via.kind) {
    case 'direct':
      return { kind: via.kind, heading: 'Direct relationship', detail: via.label }

    case 'shared_attribute':
      return {
        kind: via.kind,
        heading: `Shared ${humanizeWords(via.connector_tag).toLowerCase()}`,
        detail: `Both people hold ${via.connector_label}.`,
        connector: {
          id: via.connector_id,
          tag: via.connector_tag,
          label: via.connector_label,
        },
      }

    case 'shared_field': {
      const fields = via.field_keys.map((key) => humanizeWords(key))
      const value = displayValue ?? via.connector_label
      return {
        kind: via.kind,
        heading: via.same_key
          ? `Matching ${humanizeWords(via.field_key).toLowerCase()}`
          : 'Matching value across different fields',
        detail: via.same_key
          ? `Both documents give “${value}”.`
          : `${fields.join(' and ')} both give “${value}”.`,
        fields,
        fieldKeys: [...via.field_keys],
        matchedValue: via.connector_label,
        confidence: via.confidence,
        documentIds: via.document_ids,
      }
    }

    case 'linked_organisation':
      return {
        kind: via.kind,
        heading: 'Linked organisations',
        detail: via.label,
        connector: {
          id: via.connector_id,
          tag: via.connector_tag,
          label: via.connector_label,
        },
        linked: { id: via.linked_id, tag: via.linked_tag, label: via.linked_label },
      }
  }
}

/** The attribute cache the readable-value lookup reads. Structurally what
 * `usePersonNetworkState().attributesById` returns. */
export type AttributeIndex = Map<string, { attribute: EntityAttribute; holders: string[] }>

/** Every reason behind one link, with field matches stated in the value's
 * *readable* form.
 *
 * The projection labels a field match with the normalised index key, because
 * that's the only value the field-value vertex actually holds. Showing an
 * investigator "12alwaslroad,dubai" is useless, so this recovers the original
 * text from one of the documents that stated it — and falls back to the
 * normalised form when no citing document is loaded, rather than showing
 * nothing. */
export function describeLink(
  link: PersonLink,
  attributes: AttributeIndex,
  people?: Map<string, PersonNode>,
): ReasonDescriptor[] {
  // A field can be stated by a document or by the person vertex itself (a
  // `dob` match cites no document at all), so both are candidate sources for
  // the readable text.
  const sources = [
    ...link.via.flatMap((via) => (via.kind === 'shared_field' ? via.document_ids : [])),
  ].map((id) => attributes.get(id)?.attribute.properties)
  for (const personId of [link.source, link.target]) {
    const properties = people?.get(personId)?.properties
    if (properties) sources.push(properties)
  }

  return link.via.map((via) =>
    describeVia(
      via,
      via.kind === 'shared_field'
        ? readableMatchedValue(sources, via.field_keys, via.connector_label)
        : undefined,
    ),
  )
}

function readableMatchedValue(
  sources: (Record<string, unknown> | undefined)[],
  fieldKeys: string[],
  normalized: string,
): string | undefined {
  for (const properties of sources) {
    if (!properties) continue
    for (const key of fieldKeys) {
      const raw = properties[key]
      if (raw !== undefined && normalizeValue(raw) === normalized) return String(raw)
    }
  }
  return undefined
}

// ------------------------------------------------------- matched field index

const WHITESPACE = /\s+/g
const SEPARATORS = /[\s\-/.]/g

/** The form a value is indexed under.
 *
 * A faithful port of `normalize_value` in
 * packages/intelligence-schema/src/intelligence_schema/field_index.py, and it
 * has to stay one: this is how the panel decides whether a field on a
 * document is the field that produced a link. Get it wrong and matches go
 * silently unmarked — "12 Al Wasl Road, Dubai" is indexed as
 * "12alwaslroad,dubai", so a plain lowercase-and-trim finds nothing.
 *
 * (The Python side uses casefold() where this uses toLowerCase(); they differ
 * only for scripts this data doesn't contain, e.g. German ß.) */
function normalizeValue(value: unknown): string {
  if (value === null || value === undefined) return ''
  let text = String(value).replace(WHITESPACE, ' ').trim().toLowerCase()
  if (!text) return ''
  // Anything with a digit is treated as an identifier and loses its
  // separators, so "784-1991-7654321-2" and "784 1991 7654321 2" agree.
  if (/\d/.test(text)) text = text.replace(SEPARATORS, '')
  return text
}

/** Matched value -> the people a field match on that value connected.
 *
 * Built from the projection's own reasons rather than by comparing values
 * ourselves, so a field can be marked with *who* it matched, and so the
 * panel can never claim a match the projection didn't make (a denylisted
 * key like `nationality` appears on every document and links nobody). */
export function buildFieldMatchIndex(links: PersonLink[]): Map<string, Set<string>> {
  const index = new Map<string, Set<string>>()
  for (const link of links) {
    for (const via of link.via) {
      if (via.kind !== 'shared_field') continue
      const key = normalizeValue(via.connector_label)
      if (!key) continue
      const people = index.get(key)
      if (people) {
        people.add(link.source)
        people.add(link.target)
      } else {
        index.set(key, new Set([link.source, link.target]))
      }
    }
  }
  return index
}

// ---------------------------------------------------------- attribute fields

/** Keys that say what a document *is* rather than what it claims about a
 * person. Listed in the order they should read, and never marked as a
 * match: every passport says "passport", and the issuer is denylisted from
 * matching anyway. */
const IDENTITY_KEYS = [
  'document_type',
  'number',
  'name',
  'label',
  'issuing_country',
  'issue_date',
  'expiry_date',
]

/** Bookkeeping the graph writer stamps on every vertex. These are facts about
 * the *record*, not about the person or the document, so they'd be noise
 * among the claims — an "Entity Type: Document" row on a passport tells the
 * reader nothing they can't see in the heading. Kept out of the curated
 * views; the Raw tab still shows the whole property bag untouched. */
export const SYSTEM_KEYS = new Set([
  'confidence',
  'entity_type',
  'created_at',
  'updated_at',
  'evidence_ids',
  'props',
  // Injected by the canvas layer, never part of the stored record.
  'degree',
  'is_new',
])

/** A property bag with the bookkeeping removed, for the curated sections. */
export function factProperties(properties: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(properties ?? {}).filter(([key]) => !SYSTEM_KEYS.has(key)),
  )
}

export interface AttributeField {
  key: string
  label: string
  value: unknown
  group: 'identity' | 'claim'
  /** Other people this exact value matched, by person id. */
  matchedWith: string[]
}

/** One attribute's properties, ordered for reading and annotated with what
 * matched: identity first, then the claims that actually connected this
 * person to someone, then the rest. That ordering is the whole point — on a
 * passport with eight fields, the one that produced a link is the only one
 * an investigator is looking for. */
export function attributeFields(
  attribute: EntityAttribute,
  matches: Map<string, Set<string>>,
  holderIds: string[],
): AttributeField[] {
  const holders = new Set(holderIds)
  const fields: AttributeField[] = Object.entries(factProperties(attribute.properties)).map(
    ([key, value]) => {
      const group = IDENTITY_KEYS.includes(key) ? ('identity' as const) : ('claim' as const)
      const matchedWith =
        group === 'claim'
          ? [...(matches.get(normalizeValue(value)) ?? [])]
              .filter((id) => !holders.has(id))
              .sort()
          : []
      return { key, label: humanizeLabel(key), value, group, matchedWith }
    },
  )

  return fields.sort((a, b) => {
    if (a.group !== b.group) return a.group === 'identity' ? -1 : 1
    if (a.group === 'identity') return IDENTITY_KEYS.indexOf(a.key) - IDENTITY_KEYS.indexOf(b.key)
    const matched = Number(b.matchedWith.length > 0) - Number(a.matchedWith.length > 0)
    return matched !== 0 ? matched : a.label.localeCompare(b.label)
  })
}

// ------------------------------------------------------------------- lookups

/** The projected links a connector vertex is a reason for — "what this
 * document actually connected". Covers both a directly shared connector and
 * a field match sourced from this document. */
export function linksThroughConnector(links: PersonLink[], connectorId: string): PersonLink[] {
  return links.filter((link) =>
    link.via.some((via) => {
      if (via.kind === 'direct') return false
      if (via.connector_id === connectorId) return true
      return via.kind === 'shared_field' && via.document_ids.includes(connectorId)
    }),
  )
}

/** A person's own attributes grouped for display: documents first — they're
 * what this graph is built from — then every other tag alphabetically. */
export function groupAttributesByTag(attributes: EntityAttribute[]): [string, EntityAttribute[]][] {
  const byTag = new Map<string, EntityAttribute[]>()
  for (const attribute of attributes) {
    const list = byTag.get(attribute.tag)
    if (list) list.push(attribute)
    else byTag.set(attribute.tag, [attribute])
  }
  return [...byTag.entries()].sort(([a], [b]) => {
    if (a === b) return 0
    if (a === 'document') return -1
    if (b === 'document') return 1
    return a.localeCompare(b)
  })
}

/** The end of a link that isn't the person being viewed. */
export function otherEnd(link: PersonLink, personId: string): string {
  return link.source === personId ? link.target : link.source
}

/** How a person's distance from the searched person reads in the panel. */
export function degreeText(degree: number, rootLabel: string): string {
  if (degree === 0) return 'The person you searched for'
  return `${degree} degree${degree === 1 ? '' : 's'} from ${rootLabel}`
}
