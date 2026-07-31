import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import InfoTooltip from '../common/InfoTooltip'

interface Props {
  graphId: string
  vid: string
  isExpanded: boolean
  isExpanding: boolean
  onExpand: () => void
  onCollapse: () => void
  onClose: () => void
}

export default function NodeDetailPanel({
  graphId,
  vid,
  isExpanded,
  isExpanding,
  onExpand,
  onCollapse,
  onClose,
}: Props) {
  const nodeQuery = useQuery({
    queryKey: ['node', graphId, vid],
    queryFn: () => api.getNode(graphId, vid),
  })

  const node = nodeQuery.data

  return (
    <aside className="card stack" style={{ width: '100%', height: '100%', overflowY: 'auto' }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>Node details</h3>
        <button className="btn" onClick={onClose}>
          ✕
        </button>
      </div>

      {nodeQuery.isLoading && <p className="muted">Loading…</p>}
      {nodeQuery.isError && <p style={{ color: 'var(--color-danger)' }}>Could not load this node.</p>}

      {node && (
        <>
          <div>
            <div style={{ fontSize: '1.2em', fontWeight: 600 }}>{node.label}</div>
            <div className="muted">{node.tags.join(', ')}</div>
          </div>

          <div className="row">
            <button className="btn btn--primary" onClick={onExpand} disabled={isExpanding}>
              {isExpanding ? 'Expanding…' : 'Expand neighbors'}
            </button>
            <InfoTooltip text="Shows the other people or companies directly connected to this one, added onto the graph." />
            {isExpanded && (
              <button className="btn" onClick={onCollapse} disabled={isExpanding}>
                Collapse
              </button>
            )}
          </div>

          {node.degree.length > 0 && (
            <div>
              <h4 style={{ marginBottom: 'var(--space-2)' }}>Connections</h4>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <tbody>
                  {node.degree.map((d) => (
                    <tr key={`${d.edge_type}-${d.direction}`}>
                      <td className="muted">{d.edge_type}</td>
                      <td className="muted">{d.direction === 'out' ? '→' : '←'}</td>
                      <td style={{ textAlign: 'right' }}>{d.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div>
            <h4 style={{ marginBottom: 'var(--space-2)' }}>Properties</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <tbody>
                {Object.entries(node.properties).map(([key, value]) => (
                  <tr key={key}>
                    <td className="muted" style={{ paddingRight: 'var(--space-2)' }}>
                      {key}
                    </td>
                    <td>{value === null || value === undefined ? '—' : String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </aside>
  )
}
