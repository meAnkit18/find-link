import type {
  CancelEvidenceResponse,
  CaseCreated,
  CaseSummary,
  DeleteEvidenceResponse,
  Direction,
  EntityGraph,
  EntitySearchHit,
  EvidenceDetail,
  EvidenceSummary,
  FactReviewItem,
  GraphDetail,
  GraphNode,
  GraphSummary,
  IngestResponse,
  NodeDetail,
  NoteAdded,
  PathResult,
  ReviewItem,
  RiskExplanation,
  RiskResult,
  SchemaInfo,
  SearchResult,
  Subgraph,
  SubjectAdded,
  ToolResult,
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
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? detail)
    } catch {
      // response had no JSON body; fall back to statusText
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// Several backend routers (cases, review, agent, ingestion) declare scalar
// handler arguments, which FastAPI reads from the *query string* — even on
// POST. This helper builds those URLs, skipping empty values.
function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // -- Graphs -------------------------------------------------------------
  listGraphs: () => request<GraphSummary[]>('/api/graphs'),
  createGraph: (name: string) =>
    request<GraphSummary>('/api/graphs', { method: 'POST', body: JSON.stringify({ name }) }),
  getGraph: (graphId: string) => request<GraphDetail>(`/api/graphs/${graphId}`),
  deleteGraph: (graphId: string) => request<void>(`/api/graphs/${graphId}`, { method: 'DELETE' }),

  // -- Explorer -------------------------------------------------------------
  getSchema: (graphId: string) => request<SchemaInfo>(`/api/graphs/${graphId}/schema`),
  search: (graphId: string, q: string, limit = 50) =>
    request<SearchResult[]>(`/api/graphs/${graphId}/search${qs({ q, limit })}`),
  getNode: (graphId: string, vid: string) =>
    request<NodeDetail>(`/api/graphs/${graphId}/nodes/${encodeURIComponent(vid)}`),
  getNeighbors: (
    graphId: string,
    vid: string,
    opts: { edgeType?: string; direction?: Direction; limit?: number } = {},
  ) =>
    request<GraphNode[]>(
      `/api/graphs/${graphId}/nodes/${encodeURIComponent(vid)}/neighbors${qs({
        edge_type: opts.edgeType,
        direction: opts.direction,
        limit: opts.limit,
      })}`,
    ),
  getOverview: (graphId: string, limit = 40) =>
    request<Subgraph>(`/api/graphs/${graphId}/overview${qs({ limit })}`),

  // -- Entities ---------------------------------------------------------------
  searchEntities: (graphId: string, q: string, entityType = 'person') =>
    request<EntitySearchHit[]>(`/api/graphs/${graphId}/entities/search${qs({ q, entity_type: entityType })}`),
  getEntity: (graphId: string, entityId: string) =>
    request<Record<string, unknown>>(
      `/api/graphs/${graphId}/entities/${encodeURIComponent(entityId)}`,
    ),
  expandEntityGraph: (graphId: string, entityId: string, depth = 1) =>
    request<EntityGraph>(
      `/api/graphs/${graphId}/entities/${encodeURIComponent(entityId)}/graph${qs({ depth })}`,
    ),
  getEntityRisk: (graphId: string, entityId: string) =>
    request<RiskResult>(`/api/graphs/${graphId}/entities/${encodeURIComponent(entityId)}/risk`),
  explainEntityRisk: (graphId: string, entityId: string) =>
    request<RiskExplanation>(
      `/api/graphs/${graphId}/entities/${encodeURIComponent(entityId)}/risk/explain`,
    ),
  shortestPath: (graphId: string, source: string, target: string, maxSteps = 5) =>
    request<PathResult>(
      `/api/graphs/${graphId}/entities/shortest-path${qs({ source, target, max_steps: maxSteps })}`,
    ),

  // -- Investigations / cases -------------------------------------------------
  // NOTE: these POST endpoints take *query parameters*, not a JSON body.
  createCase: (title: string, createdBy: string, priority = 'medium') =>
    request<CaseCreated>(`/api/cases${qs({ title, created_by: createdBy, priority })}`, {
      method: 'POST',
    }),
  listCases: () => request<CaseSummary[]>('/api/cases'),
  getCase: (caseId: string) =>
    request<Record<string, unknown>>(`/api/cases/${encodeURIComponent(caseId)}`),
  addCaseSubject: (caseId: string, entityId: string, subjectRole: string, addedBy: string) =>
    request<SubjectAdded>(
      `/api/cases/${encodeURIComponent(caseId)}/subjects${qs({
        entity_id: entityId,
        subject_role: subjectRole,
        added_by: addedBy,
      })}`,
      { method: 'POST' },
    ),
  addCaseNote: (caseId: string, body: string, authorId: string) =>
    request<NoteAdded>(
      `/api/cases/${encodeURIComponent(caseId)}/notes${qs({ body, author_id: authorId })}`,
      { method: 'POST' },
    ),

  // -- Risk (default graph) -----------------------------------------------------
  calculateRisk: (entityId: string) =>
    request<RiskResult>(`/api/risk/${encodeURIComponent(entityId)}`),
  explainRisk: (entityId: string) =>
    request<RiskExplanation>(`/api/risk/${encodeURIComponent(entityId)}/explain`),

  // -- Review queue ---------------------------------------------------------------
  // graph_id is a query parameter here (the router prefix has no {graph_id}).
  listReviewItems: (graphId: string, queueType?: string) =>
    request<ReviewItem[]>(`/api/review-queue${qs({ graph_id: graphId, queue_type: queueType })}`),
  approveReview: (graphId: string, reviewId: string, reviewedBy: string, reason?: string) =>
    request<{ status: string }>(
      `/api/review-queue/${encodeURIComponent(reviewId)}/approve${qs({
        graph_id: graphId,
        reviewed_by: reviewedBy,
        reason,
      })}`,
      { method: 'POST' },
    ),
  rejectReview: (graphId: string, reviewId: string, reviewedBy: string, reason: string) =>
    request<{ status: string }>(
      `/api/review-queue/${encodeURIComponent(reviewId)}/reject${qs({
        graph_id: graphId,
        reviewed_by: reviewedBy,
        reason,
      })}`,
      { method: 'POST' },
    ),

  // -- Agent tools ------------------------------------------------------------------
  agentSearchPerson: (query: string) =>
    request<ToolResult>(`/api/agent/search-person${qs({ query })}`, { method: 'POST' }),
  agentExpandNode: (entityId: string, depth = 1) =>
    request<ToolResult>(`/api/agent/expand-node${qs({ entity_id: entityId, depth })}`, {
      method: 'POST',
    }),
  agentShortestPath: (sourceId: string, targetId: string) =>
    request<ToolResult>(
      `/api/agent/shortest-path${qs({ source_id: sourceId, target_id: targetId })}`,
      { method: 'POST' },
    ),
  agentMergeEntities: (sourceEntityId: string, targetEntityId: string) =>
    request<ToolResult>(
      `/api/agent/merge-entities${qs({
        source_entity_id: sourceEntityId,
        target_entity_id: targetEntityId,
      })}`,
      { method: 'POST' },
    ),
  agentCalculateRisk: (entityId: string) =>
    request<ToolResult>(`/api/agent/calculate-risk${qs({ entity_id: entityId })}`, {
      method: 'POST',
    }),

  // -- Evidence ingestion (unstructured data) -----------------------------
  ingestText: (text: string, sourceName: string) =>
    request<IngestResponse>('/api/evidence/ingest/text', {
      method: 'POST',
      body: JSON.stringify({ text, source_name: sourceName }),
    }),
  listEvidence: (limit = 50) => request<EvidenceSummary[]>(`/api/evidence?limit=${limit}`),
  getEvidence: (evidenceId: string) => request<EvidenceDetail>(`/api/evidence/${evidenceId}`),
  retryEvidence: (evidenceId: string) =>
    request<IngestResponse>(`/api/evidence/${evidenceId}/retry`, { method: 'POST' }),
  cancelEvidence: (evidenceId: string) =>
    request<CancelEvidenceResponse>(`/api/evidence/${evidenceId}/cancel`, { method: 'POST' }),
  deleteEvidence: (evidenceId: string, force = false) =>
    request<DeleteEvidenceResponse>(
      `/api/evidence/${evidenceId}${force ? '?force=true' : ''}`,
      { method: 'DELETE' },
    ),
  factReviewQueue: () => request<FactReviewItem[]>('/api/evidence/review/queue'),
  approveFactReview: (itemId: number) =>
    request<{ ok: boolean }>(`/api/evidence/review/${itemId}/approve`, { method: 'POST' }),
  rejectFactReview: (itemId: number) =>
    request<{ ok: boolean }>(`/api/evidence/review/${itemId}/reject`, { method: 'POST' }),

  // -- Server-side ingestion pipeline -------------------------------------------------
  ingestServerCsv: (filePath: string, sourceName: string) =>
    request<Record<string, unknown>>(
      `/api/imports/csv${qs({ file_path: filePath, source_name: sourceName })}`,
      { method: 'POST' },
    ),
  getIngestionJob: (jobId: string) =>
    request<Record<string, unknown>>(`/api/imports/${encodeURIComponent(jobId)}`),

  // -- Raw escape hatch for the API console page ---------------------------------------
  raw: (method: string, path: string, body?: string) =>
    request<unknown>(path, {
      method,
      body: body && body.trim() ? body : undefined,
    }),
}
