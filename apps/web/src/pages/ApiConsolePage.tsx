import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import RunResult from '../components/common/RunResult'

interface Preset {
  label: string
  method: string
  path: string
  body?: string
}

const PRESETS: Preset[] = [
  { label: 'List graphs', method: 'GET', path: '/api/graphs' },
  { label: 'Create graph', method: 'POST', path: '/api/graphs', body: '{"name": "test graph"}' },
  { label: 'Graph detail', method: 'GET', path: '/api/graphs/{graph_id}' },
  { label: 'Schema', method: 'GET', path: '/api/graphs/{graph_id}/schema' },
  { label: 'Overview', method: 'GET', path: '/api/graphs/{graph_id}/overview?limit=40' },
  { label: 'Search nodes', method: 'GET', path: '/api/graphs/{graph_id}/search?q=&limit=20' },
  { label: 'Node detail', method: 'GET', path: '/api/graphs/{graph_id}/nodes/{vid}' },
  { label: 'Neighbors', method: 'GET', path: '/api/graphs/{graph_id}/nodes/{vid}/neighbors?direction=both' },
  { label: 'Import job status', method: 'GET', path: '/api/graphs/{graph_id}/imports/{job_id}' },
  { label: 'Entity search', method: 'GET', path: '/api/graphs/{graph_id}/entities/search?q=&entity_type=person' },
  { label: 'Entity risk', method: 'GET', path: '/api/graphs/{graph_id}/entities/{entity_id}/risk' },
  { label: 'Shortest path', method: 'GET', path: '/api/graphs/{graph_id}/entities/shortest-path?source=&target=' },
  { label: 'List cases', method: 'GET', path: '/api/cases' },
  { label: 'Create case', method: 'POST', path: '/api/cases?title=Test&created_by=tester&priority=medium' },
  { label: 'Review queue', method: 'GET', path: '/api/review-queue?graph_id={graph_id}' },
  { label: 'Global risk', method: 'GET', path: '/api/risk/{entity_id}' },
  { label: 'Agent: search person', method: 'POST', path: '/api/agent/search-person?query=' },
  { label: 'Server-side ingest CSV', method: 'POST', path: '/api/imports/csv?file_path=/tmp/data.csv&source_name=test' },
]

/** Raw API console — hit ANY endpoint (including ones added later) without
 * leaving the browser. Presets prefill common calls; edit before sending. */
export default function ApiConsolePage() {
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('/api/graphs')
  const [body, setBody] = useState('')

  const send = useMutation({ mutationFn: () => api.raw(method, path.trim(), body) })

  return (
    <main className="page">
      <div className="container stack">
        <h2 className="page-title">API console</h2>
        <p className="muted">
          Send any request to the backend. JSON body is only sent for
          POST/PUT/PATCH; most write endpoints in this API take query
          parameters instead (already encoded in the presets).
        </p>

        <section className="card stack">
          <div className="preset-grid">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                className="btn"
                onClick={() => {
                  setMethod(p.method)
                  setPath(p.path)
                  setBody(p.body ?? '')
                }}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="row">
            <select className="select" style={{ width: 110 }} value={method} onChange={(e) => setMethod(e.target.value)}>
              {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
            <input
              className="input mono"
              style={{ flex: 1 }}
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/api/…"
            />
            <button
              className="btn btn--primary"
              disabled={!path.trim() || send.isPending}
              onClick={() => send.mutate()}
            >
              {send.isPending && <span className="spinner" />} Send
            </button>
          </div>

          {['POST', 'PUT', 'PATCH'].includes(method) && (
            <label className="field">
              <span className="field__label">JSON body (optional)</span>
              <textarea
                className="input mono"
                rows={5}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder='{"name": "value"}'
              />
            </label>
          )}

          <RunResult mutation={send} title={`${method} ${path}`} />
        </section>
      </div>
    </main>
  )
}
