import { describe, expect, it } from 'vitest'
import type { EntityAttribute } from '../../api/types'
import { attributeNodeLabel } from './attributeLabel'

function attribute(overrides: Partial<EntityAttribute> = {}): EntityAttribute {
  return {
    id: 'demo_doc_1',
    tag: 'document',
    label: 'A1122334',
    edge_type: 'HAS_DOCUMENT',
    properties: {},
    shared_with: [],
    ...overrides,
  }
}

describe('attributeNodeLabel', () => {
  it('names a document by its type instead of its number', () => {
    const node = attribute({ properties: { document_type: 'passport' } })
    expect(attributeNodeLabel(node)).toBe('Passport')
  })

  it('uppercases acronyms rather than title-casing them', () => {
    const node = attribute({ properties: { document_type: 'emirates_id' } })
    expect(attributeNodeLabel(node)).toBe('Emirates ID')
  })

  it('humanises multi-word types', () => {
    const node = attribute({ properties: { document_type: 'drivers-license' } })
    expect(attributeNodeLabel(node)).toBe('Drivers License')
  })

  it('falls back to "Document" when the type is missing', () => {
    expect(attributeNodeLabel(attribute({ properties: {} }))).toBe('Document')
  })

  it('falls back to "Document" when the type is blank or not a string', () => {
    expect(attributeNodeLabel(attribute({ properties: { document_type: '   ' } }))).toBe('Document')
    expect(attributeNodeLabel(attribute({ properties: { document_type: null } }))).toBe('Document')
    expect(attributeNodeLabel(attribute({ properties: { document_type: 7 } }))).toBe('Document')
  })

  it('renders the API’s own "document" fallback the same way', () => {
    // normalize.py / pipeline.py store the literal string "document" for
    // anything ingestion could not classify — it must not read as a type.
    const node = attribute({ properties: { document_type: 'document' } })
    expect(attributeNodeLabel(node)).toBe('Document')
  })

  it('leaves the number visible on the attribute itself', () => {
    const node = attribute({ properties: { document_type: 'passport' } })
    attributeNodeLabel(node)
    expect(node.label).toBe('A1122334')
  })

  it('passes non-document attributes through unchanged', () => {
    const node = attribute({ tag: 'phone', label: '+971500000000', properties: {} })
    expect(attributeNodeLabel(node)).toBe('+971500000000')
  })
})
