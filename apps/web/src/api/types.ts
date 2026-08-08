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

// ---------------------------------------------------------------------------
// Entities router (/api/entities/*) — always the single backing intelligence
// graph; there is no per-graph selection for these endpoints.
// ---------------------------------------------------------------------------

export interface EntitySearchHit {
  entity_id: string
  entity_type: string
  label: string
  [key: string]: unknown
}

export interface EntityGraphNode {
  id: string
  label: string
  tags: Record<string, Record<string, unknown>>
}

export interface EntityGraph {
  nodes: EntityGraphNode[]
  edges: GraphEdge[]
}

// -- Person network (the Investigation projection) ---------------------------
// The graph stores a person's phone/email/address/employer as separate
// vertices, so two people who share one are two hops apart with no edge
// between them. These types describe the *projected* person-only graph,
// where a link means "these two share something" and `via` says what.

export interface PersonNode {
  id: string
  label: string
  /** 0 for the searched person, 1/2/3 for how many connections away. */
  degree: number
  entity_type: string
  properties: Record<string, unknown>
}

export type PersonLinkVia =
  | { kind: 'direct'; edge_types: string[]; label: string }
  | {
      kind: 'shared_attribute'
      connector_id: string
      connector_tag: string
      connector_label: string
      edge_types: string[]
    }
  /** Two people whose *separate* documents agree on a value — the same
   * father's name on two passports. `connector_label` is the matched value
   * itself. */
  | {
      kind: 'shared_field'
      connector_id: string
      connector_tag: 'field_value'
      connector_label: string
      field_key: string
      field_keys: string[]
      same_key: boolean
      edge_types: string[]
      /** The documents on each side that stated the value, so a reason is
       * auditable back to its source. */
      document_ids: string[]
      confidence: number
    }
  /** Two people at *different* organisations that are themselves related —
   * "Nimbus Trade pays Meridian Exports". They share nothing; the link is
   * the relationship between their employers. */
  | {
      kind: 'linked_organisation'
      connector_id: string
      connector_tag: string
      connector_label: string
      linked_id: string
      linked_tag: string
      linked_label: string
      edge_types: string[]
      label: string
    }

export interface PersonLink {
  source: string
  target: string
  degree: number
  /** Human-readable summary of `via`, e.g. "shared phone". */
  label: string
  /** 0-1. Independent reasons compound, so this is not the best `via`'s
   * score but the noisy-OR across all of them. */
  confidence: number
  via: PersonLinkVia[]
}

/** A connector held by so many people it says nothing — reported rather
 * than silently dropped, so the canvas can admit what it left out. */
export interface SuppressedHub {
  id: string
  label: string
  tag: string
  person_count: number
}

export interface PersonNetwork {
  root_id: string
  degree: number
  min_confidence: number
  persons: PersonNode[]
  links: PersonLink[]
  truncated: boolean
  suppressed_hubs: SuppressedHub[]
  connectors: { direct: string[]; shared: string[] }
}

export interface EntityAttribute {
  id: string
  tag: string
  label: string
  edge_type: string
  properties: Record<string, unknown>
  /** Other people holding this same attribute — the reason for a link. */
  shared_with: string[]
}

export interface EntityAttributes {
  entity_id: string
  attributes: EntityAttribute[]
}

export interface PathResult {
  paths: {
    vertices: { vid: string; tags: Record<string, unknown> }[]
    edges: GraphEdge[]
  }[]
}

// ---------------------------------------------------------------------------
// Risk router (/api/risk/*, /api/graphs/{id}/entities/{id}/risk)
// ---------------------------------------------------------------------------

export interface RiskFactor {
  code: string
  weight: number
  value: number
  explanation: string
  evidence_ids: string[]
}

export interface RiskResult {
  entity_id: string
  score: number
  level: string
  factors: RiskFactor[]
}

// The explanation service returns a free-form structure; keep it loose.
export type RiskExplanation = Record<string, unknown>

// ---------------------------------------------------------------------------
// Investigations router (/api/cases)
// ---------------------------------------------------------------------------

export interface CaseSummary {
  case_id: string
  title?: string
  status?: string
  priority?: string
  created_by?: string
  [key: string]: unknown
}

export interface CaseCreated {
  case_id: string
  title: string
  status: string
}

export interface SubjectAdded {
  case_id: string
  entity_id: string
  role: string
}

export interface NoteAdded {
  note_id: string
  case_id: string
}

// ---------------------------------------------------------------------------
// Review queue router (/api/review-queue)
// ---------------------------------------------------------------------------

export interface ReviewItem {
  review_id: string
  queue_type?: string
  status?: string
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Agent tools router (/api/agent/*)
// ---------------------------------------------------------------------------

export interface ToolResult {
  ok: boolean
  data: Record<string, unknown> | null
  message: string
}

// -- Evidence ingestion pipeline --------------------------------------------

export type EvidenceStatus =
  | 'uploaded'
  | 'queued'
  | 'parsed'
  | 'extracted'
  | 'resolved'
  | 'written'
  | 'enriched'
  | 'failed'
  | 'cancelled'

export interface EvidenceSummary {
  id: string
  source_name: string
  source_type: string
  status: EvidenceStatus
  cancel_requested?: boolean
  uploaded_at: string
  error: string | null
  /** Latest processing_log entry — lets the list show live pipeline activity. */
  last_log?: ProcessingLogEntry | null
}

export interface EvidenceFact {
  id: string
  kind: 'entity' | 'relationship' | 'merge_suggestion'
  status: string
  origin: string
  confidence: number
  payload: Record<string, unknown>
}

export interface ProcessingLogEntry {
  stage: string
  at: string
  detail: string
}

export interface ExtractedEntityOut {
  local_id: string
  type: string
  name: string
  attributes: Record<string, unknown>
  confidence: number
  source_span?: string | null
}

export interface ExtractedRelationshipOut {
  source_local_id: string
  target_local_id: string
  type: string
  relation_label?: string | null
  confidence: number
  source_span?: string | null
}

export interface EvidenceDetail extends EvidenceSummary {
  sha256: string
  uploaded_by: string
  cancel_requested?: boolean
  processing_log: ProcessingLogEntry[] | null
  extraction: {
    entities?: ExtractedEntityOut[]
    relationships?: ExtractedRelationshipOut[]
    summary?: string | null
  } | null
  facts: EvidenceFact[]
}

export interface IngestResponse {
  evidence_id: string
  status: string
  source_type?: string
  note?: string
}

export interface CancelEvidenceResponse {
  evidence_id: string
  status: string
  cancel_requested: boolean
}

export interface DeleteEvidenceResponse {
  ok: boolean
  evidence_id: string
  facts_deleted: number
  review_items_deleted: number
  registry_entities_deleted: number
  graph_cleaned: boolean
}

export interface FactReviewItem {
  id: number
  fact_id: string
  evidence_id: string
  reason: string
  detail: Record<string, unknown>
  created_at: string
  kind: string | null
}
