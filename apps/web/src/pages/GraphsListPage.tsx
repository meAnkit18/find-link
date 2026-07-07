import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export default function GraphsListPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState('')

  const graphsQuery = useQuery({ queryKey: ['graphs'], queryFn: api.listGraphs })

  const createGraph = useMutation({
    mutationFn: (graphName: string) => api.createGraph(graphName),
    onSuccess: (graph) => {
      queryClient.invalidateQueries({ queryKey: ['graphs'] })
      navigate(`/graphs/${graph.id}/upload`)
    },
  })

  const deleteGraph = useMutation({
    mutationFn: (graphId: string) => api.deleteGraph(graphId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['graphs'] }),
  })

  return (
    <main className="page">
      <div className="container stack">
        <section className="card stack">
          <h2>Create a graph</h2>
          <p className="muted">
            Upload a CSV of relationships or entities and start exploring immediately — no
            query language required.
          </p>
          <form
            className="row"
            onSubmit={(e) => {
              e.preventDefault()
              if (name.trim()) createGraph.mutate(name.trim())
            }}
          >
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder='Graph name, e.g. "Q1 vendor network"'
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button className="btn btn--primary" type="submit" disabled={createGraph.isPending}>
              {createGraph.isPending ? <span className="spinner" /> : null}
              Create
            </button>
          </form>
          {createGraph.isError && (
            <p style={{ color: 'var(--color-danger)' }}>{(createGraph.error as Error).message}</p>
          )}
        </section>

        <section className="stack">
          <h2>Your graphs</h2>
          {graphsQuery.isLoading && <p className="muted">Loading…</p>}
          {graphsQuery.isError && <p style={{ color: 'var(--color-danger)' }}>Failed to load graphs.</p>}
          {graphsQuery.data?.length === 0 && (
            <p className="muted">No graphs yet — create one above to get started.</p>
          )}
          <div className="stack">
            {graphsQuery.data?.map((graph) => (
              <div key={graph.id} className="card row" style={{ justifyContent: 'space-between' }}>
                <div>
                  <Link to={`/graphs/${graph.id}`}>
                    <strong>{graph.name}</strong>
                  </Link>
                  <div className="muted">
                    {graph.vertex_count} nodes · {graph.edge_count} relationships
                  </div>
                </div>
                <div className="row">
                  <Link className="btn" to={`/graphs/${graph.id}/upload`}>
                    Import more data
                  </Link>
                  <button
                    className="btn btn--danger"
                    onClick={() => {
                      if (confirm(`Delete "${graph.name}"? This cannot be undone.`)) {
                        deleteGraph.mutate(graph.id)
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
