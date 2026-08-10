import { describe, expect, it } from 'vitest'
import type { EntityAttribute, PersonLink, PersonLinkVia } from '../../../api/types'
import {
  attributeFields,
  buildFieldMatchIndex,
  confidenceLabel,
  degreeText,
  describeLink,
  describeVia,
  factProperties,
  groupAttributesByTag,
  linksThroughConnector,
  otherEnd,
  selectionKey,
} from './detailModel'

function link(source: string, target: string, via: PersonLinkVia[], confidence = 0.5): PersonLink {
  return { source, target, degree: 1, label: 'shared', confidence, via }
}

function sharedField(value: string, opts: Partial<Extract<PersonLinkVia, { kind: 'shared_field' }>> = {}) {
  return {
    kind: 'shared_field' as const,
    connector_id: `fv_${value}`,
    connector_tag: 'field_value' as const,
    connector_label: value,
    field_key: 'father_name',
    field_keys: ['father_name'],
    same_key: true,
    edge_types: ['STATES'],
    document_ids: ['doc_a', 'doc_b'],
    confidence: 0.8,
    ...opts,
  }
}

function attribute(props: Partial<EntityAttribute> = {}): EntityAttribute {
  return {
    id: 'doc_a',
    tag: 'document',
    label: 'A1122334',
    edge_type: 'HAS_DOCUMENT',
    properties: {},
    shared_with: [],
    ...props,
  }
}

describe('selectionKey', () => {
  it('distinguishes a link from either of its endpoints', () => {
    expect(selectionKey({ kind: 'person', id: 'p1' })).toBe('person:p1')
    expect(selectionKey({ kind: 'attribute', id: 'p1' })).toBe('attribute:p1')
    expect(selectionKey({ kind: 'link', source: 'p1', target: 'p2' })).toBe('link:p1|p2')
    expect(selectionKey(null)).toBe('none')
  })
})

describe('confidenceLabel', () => {
  it('bands a score into words', () => {
    expect(confidenceLabel(0.95)).toBe('Strong')
    expect(confidenceLabel(0.7)).toBe('Strong')
    expect(confidenceLabel(0.69)).toBe('Moderate')
    expect(confidenceLabel(0.35)).toBe('Moderate')
    expect(confidenceLabel(0.34)).toBe('Weak')
    expect(confidenceLabel(0)).toBe('Weak')
  })
})

describe('describeVia', () => {
  it('reads a direct relationship as its own sentence', () => {
    const d = describeVia({ kind: 'direct', edge_types: ['RELATED_TO'], label: 'childhood friend' })
    expect(d.heading).toBe('Direct relationship')
    expect(d.detail).toBe('childhood friend')
    expect(d.connector).toBeUndefined()
  })

  it('exposes a shared attribute as an openable connector', () => {
    const d = describeVia({
      kind: 'shared_attribute',
      connector_id: 'doc_dup',
      connector_tag: 'document',
      connector_label: 'E7654321',
      edge_types: ['HAS_DOCUMENT'],
    })
    expect(d.heading).toBe('Shared document')
    expect(d.detail).toContain('E7654321')
    expect(d.connector?.id).toBe('doc_dup')
  })

  it('keeps the field-value vertex unopenable and offers the documents instead', () => {
    // The field-value index is deliberately not on the canvas, so offering
    // it as a connector would select a node that does not exist.
    const d = describeVia(sharedField('Ibrahim Rahman'))
    expect(d.connector).toBeUndefined()
    expect(d.documentIds).toEqual(['doc_a', 'doc_b'])
    expect(d.heading).toBe('Matching father name')
    expect(d.confidence).toBe(0.8)
  })

  it('names both fields when a value matched across different keys', () => {
    const d = describeVia(
      sharedField('88 Marina Walk, Dubai', {
        same_key: false,
        field_key: 'address',
        field_keys: ['address', 'residence_address'],
      }),
    )
    expect(d.heading).toBe('Matching value across different fields')
    expect(d.detail).toBe('Address and Residence Address both give “88 Marina Walk, Dubai”.')
  })

  it('carries both organisations for a linked-organisation reason', () => {
    const d = describeVia({
      kind: 'linked_organisation',
      connector_id: 'org_nimbus',
      connector_tag: 'organisation',
      connector_label: 'Nimbus Trade',
      linked_id: 'org_meridian',
      linked_tag: 'organisation',
      linked_label: 'Meridian Exports',
      edge_types: ['PAYS'],
      label: 'Nimbus Trade pays Meridian Exports',
    })
    expect(d.connector?.id).toBe('org_nimbus')
    expect(d.linked?.id).toBe('org_meridian')
  })
})

describe('describeLink', () => {
  // The projection labels a field match with the *normalised* index key, so
  // an address arrives as "12alwaslroad,dubai". Showing that to an
  // investigator is useless — the readable text has to come back from the
  // document that stated it.
  const via = sharedField('12alwaslroad,dubai', { field_key: 'address', field_keys: ['address'] })
  const l = link('p_yusuf', 'p_khalid', [via])

  it('recovers the readable value from a citing document', () => {
    const index = new Map([
      [
        'doc_a',
        {
          attribute: attribute({
            id: 'doc_a',
            properties: { address: '12 Al Wasl Road, Dubai' },
          }),
          holders: ['p_yusuf'],
        },
      ],
    ])
    expect(describeLink(l, index)[0].detail).toBe('Both documents give “12 Al Wasl Road, Dubai”.')
  })

  it('falls back to the normalised value when no citing document is loaded', () => {
    expect(describeLink(l, new Map())[0].detail).toBe('Both documents give “12alwaslroad,dubai”.')
  })

  it('leaves reasons that are not field matches alone', () => {
    const direct = link('p1', 'p2', [{ kind: 'direct', edge_types: ['RELATED_TO'], label: 'spouse' }])
    expect(describeLink(direct, new Map())[0].detail).toBe('spouse')
  })
})

describe('factProperties', () => {
  it('drops the graph writer’s bookkeeping', () => {
    expect(
      factProperties({
        entity_type: 'Document',
        confidence: 1,
        created_at: 123,
        updated_at: 124,
        evidence_ids: '[]',
        degree: 2,
        is_new: true,
        father_name: 'Ibrahim Rahman',
      }),
    ).toEqual({ father_name: 'Ibrahim Rahman' })
  })
})

describe('buildFieldMatchIndex', () => {
  it('indexes both people behind every field match, case-insensitively', () => {
    const index = buildFieldMatchIndex([
      link('p_amina', 'p_yusuf', [sharedField('Ibrahim Rahman')]),
      link('p_yusuf', 'p_khalid', [sharedField('12alwaslroad,dubai')]),
    ])
    expect(index.get('ibrahim rahman')).toEqual(new Set(['p_amina', 'p_yusuf']))
    expect(index.get('12alwaslroad,dubai')).toEqual(new Set(['p_yusuf', 'p_khalid']))
  })

  it('normalizes exactly as the field index does, so digit-bearing values match', () => {
    // Mirrors normalize_value in intelligence_schema/field_index.py: a value
    // containing a digit loses its separators. A plain lowercase-and-trim
    // would leave "12 al wasl road, dubai" and never match the projection's
    // key, so every address match would go unflagged.
    const index = buildFieldMatchIndex([
      link('p_yusuf', 'p_khalid', [sharedField('12alwaslroad,dubai')]),
    ])
    const flagged = attributeFields(
      attribute({ properties: { address: '12 Al Wasl Road, Dubai' } }),
      index,
      ['p_yusuf'],
    )
    expect(flagged[0].matchedWith).toEqual(['p_khalid'])
  })

  it('matches an id written with different separators', () => {
    const index = buildFieldMatchIndex([
      link('p1', 'p2', [sharedField('784199176543212', { field_key: 'id_number' })]),
    ])
    const flagged = attributeFields(
      attribute({ properties: { id_number: '784-1991-7654321-2' } }),
      index,
      ['p1'],
    )
    expect(flagged[0].matchedWith).toEqual(['p2'])
  })

  it('ignores reasons that are not field matches', () => {
    const index = buildFieldMatchIndex([
      link('p1', 'p2', [{ kind: 'direct', edge_types: ['RELATED_TO'], label: 'spouse' }]),
    ])
    expect(index.size).toBe(0)
  })
})

describe('attributeFields', () => {
  const matches = buildFieldMatchIndex([
    link('p_amina', 'p_yusuf', [sharedField('Ibrahim Rahman')]),
  ])

  const fields = attributeFields(
    attribute({
      properties: {
        place_of_birth: 'Dubai',
        father_name: 'Ibrahim Rahman',
        number: 'A1122334',
        document_type: 'passport',
        mother_name: 'Fatima Rahman',
      },
    }),
    matches,
    ['p_amina'],
  )

  it('puts identity fields first, in reading order', () => {
    expect(fields.slice(0, 2).map((f) => f.key)).toEqual(['document_type', 'number'])
    expect(fields.slice(0, 2).every((f) => f.group === 'identity')).toBe(true)
  })

  it('lifts a claim that produced a match above the claims that did not', () => {
    const claims = fields.filter((f) => f.group === 'claim').map((f) => f.key)
    expect(claims[0]).toBe('father_name')
    expect(claims.slice(1)).toEqual(['mother_name', 'place_of_birth'])
  })

  it('names who a matched value connected, excluding the holder', () => {
    const father = fields.find((f) => f.key === 'father_name')
    expect(father?.matchedWith).toEqual(['p_yusuf'])
    expect(fields.find((f) => f.key === 'mother_name')?.matchedWith).toEqual([])
  })

  it('never marks an identity field as a match', () => {
    // Two people sharing a document type is not a finding, so even if a
    // value collides the identity half stays unmarked.
    const collides = attributeFields(
      attribute({ properties: { document_type: 'Ibrahim Rahman' } }),
      matches,
      ['p_amina'],
    )
    expect(collides[0].matchedWith).toEqual([])
  })

  it('humanizes keys for display', () => {
    expect(fields.find((f) => f.key === 'place_of_birth')?.label).toBe('Place Of Birth')
  })
})

describe('linksThroughConnector', () => {
  const shared = link('p1', 'p2', [
    {
      kind: 'shared_attribute',
      connector_id: 'doc_dup',
      connector_tag: 'document',
      connector_label: 'E7654321',
      edge_types: ['HAS_DOCUMENT'],
    },
  ])
  const fieldMatch = link('p3', 'p4', [sharedField('Ibrahim Rahman')])
  const direct = link('p5', 'p6', [{ kind: 'direct', edge_types: ['RELATED_TO'], label: 'spouse' }])
  const links = [shared, fieldMatch, direct]

  it('finds links a shared connector explains', () => {
    expect(linksThroughConnector(links, 'doc_dup')).toEqual([shared])
  })

  it('finds links a document explains through a field match', () => {
    expect(linksThroughConnector(links, 'doc_a')).toEqual([fieldMatch])
  })

  it('returns nothing for a connector no link mentions', () => {
    expect(linksThroughConnector(links, 'doc_unrelated')).toEqual([])
  })
})

describe('groupAttributesByTag', () => {
  it('groups by tag with documents first', () => {
    const grouped = groupAttributesByTag([
      attribute({ id: 'ph1', tag: 'phone', label: '+971 50 111' }),
      attribute({ id: 'd1', tag: 'document', label: 'A1' }),
      attribute({ id: 'a1', tag: 'address', label: '12 Al Wasl' }),
      attribute({ id: 'd2', tag: 'document', label: 'A2' }),
    ])
    expect(grouped.map(([tag, list]) => [tag, list.length])).toEqual([
      ['document', 2],
      ['address', 1],
      ['phone', 1],
    ])
  })
})

describe('otherEnd / degreeText', () => {
  it('returns the far end of a link', () => {
    const l = link('p1', 'p2', [])
    expect(otherEnd(l, 'p1')).toBe('p2')
    expect(otherEnd(l, 'p2')).toBe('p1')
  })

  it('phrases distance from the searched person', () => {
    expect(degreeText(0, 'Amina Rahman')).toBe('The person you searched for')
    expect(degreeText(1, 'Amina Rahman')).toBe('1 degree from Amina Rahman')
    expect(degreeText(3, 'Amina Rahman')).toBe('3 degrees from Amina Rahman')
  })
})
