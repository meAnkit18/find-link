import type { SchemaInfo } from '../../api/types'
import InfoTooltip from '../common/InfoTooltip'

interface Props {
  schema: SchemaInfo
  hiddenTags: Set<string>
  hiddenEdgeTypes: Set<string>
  onToggleTag: (tag: string) => void
  onToggleEdgeType: (edgeType: string) => void
}

export default function FilterPanel({
  schema,
  hiddenTags,
  hiddenEdgeTypes,
  onToggleTag,
  onToggleEdgeType,
}: Props) {
  return (
    <div className="card stack" style={{ width: '100%' }}>
      <div>
        <h4 style={{ marginBottom: 'var(--space-2)' }}>
          Node types
          <InfoTooltip text="Untick a type to hide those items from the graph. Doesn't delete anything — just hides them from view." />
        </h4>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {schema.tags.map((tag) => (
            <label key={tag} className="row" style={{ gap: 'var(--space-2)' }}>
              <input
                type="checkbox"
                checked={!hiddenTags.has(tag)}
                onChange={() => onToggleTag(tag)}
              />
              {tag}
            </label>
          ))}
        </div>
      </div>
      <div>
        <h4 style={{ marginBottom: 'var(--space-2)' }}>
          Relationship types
          <InfoTooltip text="Untick a type to hide those connections from the graph. Doesn't delete anything — just hides them from view." />
        </h4>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {schema.edge_types.map((edgeType) => (
            <label key={edgeType} className="row" style={{ gap: 'var(--space-2)' }}>
              <input
                type="checkbox"
                checked={!hiddenEdgeTypes.has(edgeType)}
                onChange={() => onToggleEdgeType(edgeType)}
              />
              {edgeType}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
