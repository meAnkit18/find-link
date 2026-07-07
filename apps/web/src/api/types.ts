// Mirrors the Pydantic response models in apps/api/src/graph_explorer_api/routers/*.py.
// Kept as one file since the two sides (this + the API) must be changed
// together — a mismatch here is a silent runtime bug, not a compile error.

export interface GraphSummary {
  id: string
  name: string
  created_at: string
  vertex_count: number
  edge_count: number
}

export interface GraphDetail extends GraphSummary {
  tags: string[]
  edge_types: string[]
}

export interface ImportReport {
  filename: string
  structure_kind: 'edge_list' | 'node_table'
  tag: string | null
  edge_type: string | null
  rows_read: number
  vertices_created: number
  edges_created: number
  duplicates_skipped: number
  validation_errors: string[]
  elapsed_seconds: number
}

export type ImportJobStatus = 'pending' | 'running' | 'done' | 'failed'

export interface ImportJob {
  job_id: string
  graph_id: string
  filename: string
  status: ImportJobStatus
  report: ImportReport | null
  error: string | null
}

export interface SchemaInfo {
  tags: string[]
  edge_types: string[]
}

export interface SearchResult {
  vid: string
  tag: string
  label: string
}

export interface GraphNode {
  vid: string
  tags: string[]
  label: string
  properties: Record<string, unknown>
}

export interface DegreeEntry {
  edge_type: string
  direction: 'out' | 'in'
  count: number
}

export interface NodeDetail extends GraphNode {
  degree: DegreeEntry[]
}

export interface GraphEdge {
  src: string
  dst: string
  edge_type: string
  rank: number
  properties: Record<string, unknown>
}

export interface Subgraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type Direction = 'out' | 'in' | 'both'
