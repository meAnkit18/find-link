import type { SchemaInfo } from '../../api/types'
import InfoTooltip from '../common/InfoTooltip'
import { colorForTag } from './graphStyle'

interface Props {
  schema: SchemaInfo
  hiddenTags: Set<string>
  hiddenEdgeTypes: Set<string>
  mainTags: Set<string>
  onToggleTag: (tag: string) => void
  onToggleEdgeType: (edgeType: string) => void
  onToggleMainTag: (tag: string) => void
}

export default function FilterPanel({
  schema,
  hiddenTags,
  hiddenEdgeTypes,
  mainTags,
  onToggleTag,
  onToggleEdgeType,
  onToggleMainTag,
}: Props) {
  return (
    <div className="card stack" style={{ width: '100%' }}>
      <div>
        <h4 style={{ marginBottom: 'var(--space-2)' }}>
          Node types
          <InfoTooltip text="Untick a type to hide those items from the graph. Star a type to treat it as a main node: the graph will show only starred types at first, and clicking one reveals everything connected to it." />
        </h4>
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          {schema.tags.map((tag) => (
            <div key={tag} className="row" style={{ gap: 'var(--space-2)', justifyContent: 'space-between' }}>
              <label className="row" style={{ gap: 'var(--space-2)' }}>
                <input
                  type="checkbox"
                  checked={!hiddenTags.has(tag)}
                  onChange={() => onToggleTag(tag)}
                />
                <span className="tag-dot" style={{ background: colorForTag(tag) }} />
                {tag}
              </label>
              <button
                type="button"
                className="btn btn-sm"
                aria-pressed={mainTags.has(tag)}
                title={mainTags.has(tag) ? 'Main node type — click to unset' : 'Set as a main node type'}
                onClick={() => onToggleMainTag(tag)}
                style={{ color: mainTags.has(tag) ? 'var(--color-primary)' : undefined }}
              >
                ★
              </button>
            </div>
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
