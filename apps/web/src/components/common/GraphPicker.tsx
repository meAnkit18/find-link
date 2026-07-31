import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import InfoTooltip from './InfoTooltip'

interface Props {
  value: string
  onChange: (graphId: string) => void
  label?: string
  info?: string
}

/** Dropdown of all graphs — used by pages whose endpoints need a graph_id. */
export default function GraphPicker({ value, onChange, label = 'Graph', info }: Props) {
  const graphsQuery = useQuery({ queryKey: ['graphs'], queryFn: api.listGraphs })
  const graphs = graphsQuery.data ?? []

  return (
    <label className="field">
      {label && (
        <span className="field__label">
          {label}
          {info && <InfoTooltip text={info} />}
        </span>
      )}
      <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">— select a graph —</option>
        {graphs.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name} ({g.vertex_count} nodes)
          </option>
        ))}
      </select>
    </label>
  )
}
