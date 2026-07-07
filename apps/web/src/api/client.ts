import type {
  Direction,
  GraphDetail,
  GraphSummary,
  ImportJob,
  NodeDetail,
  SchemaInfo,
  SearchResult,
  Subgraph,
  GraphNode,
} from './types'

// Empty base + Vite's dev proxy (see vite.config.ts) means the same fetch
// paths work in dev and in a same-origin production deploy; set
// VITE_API_BASE_URL to point at a different origin instead.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  listGraphs: () => request<GraphSummary[]>('/api/graphs'),
  createGraph: (name: string) =>
    request<GraphSummary>('/api/graphs', { method: 'POST', body: JSON.stringify({ name }) }),
  getGraph: (graphId: string) => request<GraphDetail>(`/api/graphs/${graphId}`),
  deleteGraph: (graphId: string) => request<void>(`/api/graphs/${graphId}`, { method: 'DELETE' }),

  startImport: (graphId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportJob>(`/api/graphs/${graphId}/imports`, { method: 'POST', body: form })
  },
  getImportJob: (graphId: string, jobId: string) =>
    request<ImportJob>(`/api/graphs/${graphId}/imports/${jobId}`),

  getSchema: (graphId: string) => request<SchemaInfo>(`/api/graphs/${graphId}/schema`),
  search: (graphId: string, q: string, limit = 50) =>
    request<SearchResult[]>(
      `/api/graphs/${graphId}/search?${new URLSearchParams({ q, limit: String(limit) })}`,
    ),
  getNode: (graphId: string, vid: string) =>
    request<NodeDetail>(`/api/graphs/${graphId}/nodes/${encodeURIComponent(vid)}`),
  getNeighbors: (
    graphId: string,
    vid: string,
    opts: { edgeType?: string; direction?: Direction; limit?: number } = {},
  ) => {
    const params = new URLSearchParams()
    if (opts.edgeType) params.set('edge_type', opts.edgeType)
    if (opts.direction) params.set('direction', opts.direction)
    if (opts.limit) params.set('limit', String(opts.limit))
    return request<GraphNode[]>(
      `/api/graphs/${graphId}/nodes/${encodeURIComponent(vid)}/neighbors?${params}`,
    )
  },
  getOverview: (graphId: string, limit = 40) =>
    request<Subgraph>(`/api/graphs/${graphId}/overview?${new URLSearchParams({ limit: String(limit) })}`),
}
