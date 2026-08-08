import { formatPropertyValue, humanizeLabel } from './format'

function renderValue(value: unknown) {
  const formatted = formatPropertyValue(value)
  switch (formatted.kind) {
    case 'empty':
      return <span className="muted">Not recorded</span>
    case 'list':
      return (
        <div className="row" style={{ flexWrap: 'wrap', gap: 4 }}>
          {formatted.items.map((item, i) => (
            <span key={i} className="badge">
              {item}
            </span>
          ))}
        </div>
      )
    case 'code':
      return <span className="mono">{formatted.text}</span>
    case 'text':
      return formatted.text
  }
}

interface Props {
  properties: Record<string, unknown>
  emptyLabel?: string
}

/** A person/attribute's raw properties, laid out as a readable label/value
 * list instead of pretty-printed JSON — the source data's schema is
 * arbitrary, so keys are humanized and values are formatted by type. */
export default function PropertiesList({ properties, emptyLabel = 'No properties recorded.' }: Props) {
  const entries = Object.entries(properties ?? {})
  if (entries.length === 0) return <p className="text-secondary">{emptyLabel}</p>

  return (
    <dl className="prop-list">
      {entries.map(([key, value]) => (
        <div className="prop-list__row" key={key}>
          <dt className="prop-list__key">{humanizeLabel(key)}</dt>
          <dd className="prop-list__value">{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  )
}
