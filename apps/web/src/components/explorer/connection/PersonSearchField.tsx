import { useState } from 'react'
import { Search } from 'lucide-react'
import { api } from '../../../api/client'
import type { EntitySearchHit } from '../../../api/types'
import { PERSON_TAG } from '../../../hooks/usePersonNetworkState'

interface Props {
  label: string
  placeholder: string
  selected: EntitySearchHit | null
  onSelect: (hit: EntitySearchHit | null) => void
}

/** A type-and-pick person search box, self-contained so the connection
 * finder can show two of them side by side without sharing state — one and
 * the same pattern as the single-person search on the Investigation page,
 * just parameterized for a slot instead of the page's own state. */
export default function PersonSearchField({ label, placeholder, selected, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EntitySearchHit[]>([])
  const [error, setError] = useState<string | null>(null)

  async function search() {
    if (!query.trim()) return
    setError(null)
    try {
      const hits = await api.searchEntities(query.trim(), PERSON_TAG)
      setResults(hits)
      if (hits.length === 0) setError('No people matched.')
    } catch (err) {
      setResults([])
      setError((err as Error).message)
    }
  }

  if (selected) {
    return (
      <div className="connection-picker">
        <span className="connection-picker__label">{label}</span>
        <div className="connection-picker__chosen">
          <strong>{selected.label || selected.entity_id}</strong>
          <button className="btn btn-sm" onClick={() => onSelect(null)}>
            Change
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="connection-picker" style={{ position: 'relative' }}>
      <span className="connection-picker__label">{label}</span>
      <div className="row" style={{ gap: 'var(--space-1)' }}>
        <div className="search-input-wrap">
          <Search className="search-input-wrap__icon" size={14} />
          <input
            className="input input--search"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <button className="btn btn-sm" onClick={search}>
          Search
        </button>
      </div>
      {error && (
        <div className="muted" style={{ marginTop: 'var(--space-1)' }}>
          {error}
        </div>
      )}
      {results.length > 0 && (
        <div className="card search-dropdown">
          {results.map((hit) => (
            <button
              key={hit.entity_id}
              className="list-item"
              onClick={() => {
                onSelect(hit)
                setResults([])
                setQuery('')
              }}
            >
              <strong>{hit.label || hit.entity_id}</strong>
              <div className="mono muted">{hit.entity_id}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
