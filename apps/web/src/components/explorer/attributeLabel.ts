import type { EntityAttribute } from '../../api/types'

const DOCUMENT_TAG = 'document'

/** Shown when a document carries no usable type. Ingestion already stores
 * the literal string "document" for anything it could not classify (see
 * normalize.py / pipeline.py), so that value humanises to this same word —
 * both the missing and the unclassified case read alike, on purpose. */
const UNTYPED_DOCUMENT = 'Document'

// Words that are initialisms, not words: title-casing them gives "Emirates
// Id", which reads as a typo. Kept deliberately short — add only what the
// data actually contains.
const ACRONYMS = new Set(['id', 'uae'])

/** Title-case a snake/kebab/spaced identifier, keeping known initialisms
 * upper — "emirates_id" reads as "Emirates ID", not "Emirates Id".
 *
 * Exported because the detail panel humanizes the same vocabulary (tags,
 * document field keys) and the ACRONYMS list has to stay in one place. Use
 * `humanizeLabel` from common/format for plain keys with no initialisms. */
export function humanizeWords(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase()
      if (ACRONYMS.has(lower)) return lower.toUpperCase()
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
}

/** What a sub-node should be called on the canvas.
 *
 * A document vertex's own label is its number ("A1122334"), which is an
 * identifier, not a name — on a graph it says nothing about what the node
 * is. So documents are labelled by their kind ("Passport", "Emirates ID")
 * and the number stays in `label`/`properties` for the popup and the detail
 * panel, where an investigator can actually read it.
 *
 * Everything else passes through untouched. Only `document` is expandable
 * today, so in practice every sub-node takes the first branch; the guard is
 * so that making phones or emails expandable later doesn't silently rename
 * them too.
 */
export function attributeNodeLabel(attribute: EntityAttribute): string {
  if (attribute.tag !== DOCUMENT_TAG) return attribute.label

  const documentType = attribute.properties?.document_type
  if (typeof documentType !== 'string') return UNTYPED_DOCUMENT

  return humanizeWords(documentType) || UNTYPED_DOCUMENT
}
