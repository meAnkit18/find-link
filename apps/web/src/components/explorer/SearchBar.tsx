import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { SearchResult } from '../../api/types'

interface Props {
  graphId: string
  onResultClick: (result: SearchResult) => void
}

export default function SearchBar({ graphId, onResultClick }: Props) {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setQuery(input), 250)
    return () => clearTimeout(timer)
  }, [input])

  const searchQuery = useQuery({
    queryKey: ['search', graphId, query],
    queryFn: () => api.search(graphId, query, 20),
    enabled: query.length > 0,
  })

  const results = query ? searchQuery.data ?? [] : []

  return (
    <div style={{ position: 'relative' }}>
      <input
        className="input"
        style={{ width: '100%' }}
        placeholder="Search nodes by name…"
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      {results.length > 0 && (
        <div
          className="card"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            maxHeight: 320,
            overflowY: 'auto',
            zIndex: 20,
            padding: 'var(--space-2)',
          }}
        >
          {results.map((result) => (
            <button
              key={`${result.tag}:${result.vid}`}
              className="btn"
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                border: 'none',
                background: 'none',
              }}
              onClick={() => {
                onResultClick(result)
                setInput('')
                setQuery('')
              }}
            >
              <strong>{result.label}</strong>{' '}
              <span className="muted">({result.tag})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
