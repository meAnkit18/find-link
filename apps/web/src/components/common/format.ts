/** "date_of_birth" -> "Date Of Birth" — the source data's schema is
 * arbitrary (tag names, property keys), so this is used anywhere a raw
 * identifier needs to read as a human label instead. */
export function humanizeLabel(text: string): string {
  return text
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// Property values coming off the graph are whatever the source data had:
// plain scalars almost always, but ingestion can also leave behind arrays
// (e.g. multiple phone numbers) or a nested object. Each gets a rendering
// that stays readable instead of falling back to a JSON dump.
export function formatPropertyValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return { kind: 'empty' as const }
  }
  if (typeof value === 'boolean') return { kind: 'text' as const, text: value ? 'Yes' : 'No' }
  if (Array.isArray(value)) {
    if (value.length === 0) return { kind: 'empty' as const }
    return {
      kind: 'list' as const,
      items: value.map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item))),
    }
  }
  if (typeof value === 'object') {
    return { kind: 'code' as const, text: JSON.stringify(value) }
  }
  if (typeof value === 'string') {
    // Dates are stored as ISO strings — show them in a form a person
    // actually reads instead of the raw "2024-03-01T00:00:00" text.
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
      const parsed = new Date(value)
      if (!Number.isNaN(parsed.getTime())) {
        return {
          kind: 'text' as const,
          text: parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }),
        }
      }
    }
  }
  return { kind: 'text' as const, text: String(value) }
}
