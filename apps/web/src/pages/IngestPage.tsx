import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { EvidenceDetail, EvidenceSummary, ProcessingLogEntry } from '../api/types'

const INTEL_GRAPH_ID = 'intelligence_graph'

const STAGES = ['parsed', 'extracted', 'resolved', 'written', 'enriched'] as const
const STAGE_VERBS = ['parse', 'extract', 'resolve', 'write', 'enrich'] as const
const ACTIVE = new Set(['uploaded', 'queued', 'parsed', 'extracted', 'resolved', 'written'])
const TERMINAL = new Set(['enriched', 'failed', 'cancelled'])

function stageIndex(status: string): number {
  return STAGES.indexOf(status as (typeof STAGES)[number])
}

/** Which stage did a failed item die in? The error is "stage: message". */
function failedStageIndex(error: string | null | undefined): number {
  if (!error) return -1
  const prefix = error.split(':')[0]?.trim()
  return STAGE_VERBS.indexOf(prefix as (typeof STAGE_VERBS)[number])
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

function StatusChip({ status, cancelRequested }: { status: string; cancelRequested?: boolean }) {
  const stopping = cancelRequested && ACTIVE.has(status)
  const color =
    status === 'failed'
      ? 'var(--color-danger)'
      : status === 'cancelled' || stopping
        ? 'var(--color-muted, #888)'
        : status === 'enriched' || status === 'written'
          ? 'var(--color-success, #2e7d32)'
          : 'var(--color-primary)'
  return (
    <span
      className="badge"
      style={{ borderColor: color, color, display: 'inline-flex', gap: 6, alignItems: 'center' }}
    >
      {ACTIVE.has(status) && <span className="spinner" style={{ width: 10, height: 10 }} />}
      {stopping ? `${status} — stopping…` : status}
    </span>
  )
}

/**
 * Live stage strip: completed stages are lit, the stage the pipeline is
 * currently in gets a spinner, and for failed items the stage that broke is
 * shown in red.
 */
function PipelineProgress({ status, error }: { status: string; error?: string | null }) {
  const reached = stageIndex(status)
  const failedAt = status === 'failed' ? failedStageIndex(error) : -1
  const runningIdx = ACTIVE.has(status) ? reached + 1 : -1
  return (
    <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
      {STAGES.map((stage, i) => {
        const done = failedAt >= 0 ? i < failedAt : reached >= i
        const isRunning = i === runningIdx && runningIdx < STAGES.length
        const isFailed = i === failedAt
        const border = isFailed
          ? 'var(--color-danger)'
          : done || isRunning
            ? 'var(--color-primary)'
            : 'var(--color-border)'
        return (
          <span
            key={stage}
            className="badge"
            style={{
              opacity: done || isRunning || isFailed ? 1 : 0.35,
              borderColor: border,
              color: isFailed ? 'var(--color-danger)' : undefined,
              display: 'inline-flex',
              gap: 4,
              alignItems: 'center',
            }}
          >
            {isRunning && <span className="spinner" style={{ width: 8, height: 8 }} />}
            {i + 1}. {stage}
            {isFailed && ' ✕'}
          </span>
        )
      })}
    </div>
  )
}

/** Always-visible, auto-updating log of everything the pipeline is doing. */
function LiveLog({ log, active }: { log: ProcessingLogEntry[]; active: boolean }) {
  if (log.length === 0) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        {active ? 'Waiting for the pipeline to pick this up…' : 'No processing activity recorded.'}
      </p>
    )
  }
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '0.85em',
        background: 'var(--color-surface-2, rgba(0,0,0,0.04))',
        border: '1px solid var(--color-border)',
        borderRadius: 6,
        padding: '8px 10px',
        maxHeight: 220,
        overflowY: 'auto',
      }}
    >
      {log.map((entry, i) => {
        const isLast = i === log.length - 1
        const failed = (entry.detail ?? '').startsWith('FAILED')
        return (
          <div key={i} className="row" style={{ gap: 8, alignItems: 'baseline', flexWrap: 'nowrap' }}>
            <span className="muted" style={{ whiteSpace: 'nowrap' }}>{fmtTime(entry.at)}</span>
            <span
              className="badge"
              style={{
                flexShrink: 0,
                borderColor: failed ? 'var(--color-danger)' : undefined,
                color: failed ? 'var(--color-danger)' : undefined,
              }}
            >
              {entry.stage}
            </span>
            <span style={{ color: failed ? 'var(--color-danger)' : undefined }}>
              {entry.detail}
              {isLast && active && (
                <span className="spinner" style={{ width: 9, height: 9, marginLeft: 6, display: 'inline-block' }} />
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function EvidenceDetailView({ detail }: { detail: EvidenceDetail }) {
  const entities = detail.extraction?.entities ?? []
  const relationships = detail.extraction?.relationships ?? []
  const byLocalId = useMemo(
    () => new Map(entities.map((e) => [e.local_id, e.name])),
    [entities],
  )
  const active = ACTIVE.has(detail.status)
  return (
    <div className="stack" style={{ gap: 'var(--space-3)' }}>
      <div>
        <h4 style={{ margin: '0 0 4px' }}>Live pipeline activity</h4>
        <LiveLog log={detail.processing_log ?? []} active={active} />
      </div>

      {detail.extraction?.summary && (
        <p style={{ margin: 0 }}>
          <strong>Summary:</strong> {detail.extraction.summary}
        </p>
      )}
      {detail.error && (
        <p style={{ color: 'var(--color-danger)', margin: 0, whiteSpace: 'pre-wrap' }}>
          {detail.error}
        </p>
      )}

      {entities.length > 0 && (
        <div>
          <h4 style={{ margin: '0 0 4px' }}>Entities ({entities.length})</h4>
          <table className="table">
            <thead>
              <tr><th>Type</th><th>Name</th><th>Confidence</th><th>Source span</th></tr>
            </thead>
            <tbody>
              {entities.map((e) => (
                <tr key={e.local_id}>
                  <td><span className="badge">{e.type}</span></td>
                  <td>{e.name}</td>
                  <td>{(e.confidence * 100).toFixed(0)}%</td>
                  <td className="muted" style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.source_span ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {relationships.length > 0 && (
        <div>
          <h4 style={{ margin: '0 0 4px' }}>Relationships ({relationships.length})</h4>
          <table className="table">
            <thead>
              <tr><th>Source</th><th>Type</th><th>Target</th><th>Confidence</th></tr>
            </thead>
            <tbody>
              {relationships.map((r, i) => (
                <tr key={i}>
                  <td>{byLocalId.get(r.source_local_id) ?? r.source_local_id}</td>
                  <td>
                    <span className="badge">
                      {r.type === 'RELATED_TO' && r.relation_label ? r.relation_label : r.type}
                    </span>
                  </td>
                  <td>{byLocalId.get(r.target_local_id) ?? r.target_local_id}</td>
                  <td>{(r.confidence * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function IngestPage() {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [sourceName, setSourceName] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)

  const evidenceQuery = useQuery({
    queryKey: ['evidence-list'],
    queryFn: () => api.listEvidence(50),
    refetchInterval: (query) => {
      const rows = query.state.data as EvidenceSummary[] | undefined
      return rows?.some((r) => ACTIVE.has(r.status)) ? 1500 : 8000
    },
  })

  const detailQuery = useQuery({
    queryKey: ['evidence', selectedId],
    queryFn: () => api.getEvidence(selectedId!),
    enabled: Boolean(selectedId),
    refetchInterval: (query) => {
      const d = query.state.data as EvidenceDetail | undefined
      return d && ACTIVE.has(d.status) ? 1500 : false
    },
  })

  const reviewQuery = useQuery({
    queryKey: ['fact-review'],
    queryFn: () => api.factReviewQueue(),
    refetchInterval: 5000,
  })

  const refreshList = () => {
    queryClient.invalidateQueries({ queryKey: ['evidence-list'] })
    if (selectedId) queryClient.invalidateQueries({ queryKey: ['evidence', selectedId] })
  }

  const afterIngest = (evidenceId: string, note?: string) => {
    setFlash(note === 'duplicate' ? 'Already ingested (duplicate content).' : null)
    setSelectedId(evidenceId)
    queryClient.invalidateQueries({ queryKey: ['evidence-list'] })
  }

  const ingestText = useMutation({
    mutationFn: () => api.ingestText(text, sourceName.trim() || 'manual-text'),
    onSuccess: (res) => {
      setText('')
      afterIngest(res.evidence_id, res.note)
    },
  })
  const retry = useMutation({
    mutationFn: (id: string) => api.retryEvidence(id),
    onSuccess: () => { setRowError(null); refreshList() },
    onError: (err, id) => setRowError({ id, message: (err as Error).message }),
  })
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelEvidence(id),
    onSuccess: () => { setRowError(null); refreshList() },
    onError: (err, id) => setRowError({ id, message: (err as Error).message }),
  })
  const deleteEv = useMutation({
    mutationFn: ({ id, force }: { id: string; force?: boolean }) =>
      api.deleteEvidence(id, force),
    onSuccess: (res) => {
      setRowError(null)
      if (selectedId === res.evidence_id) setSelectedId(null)
      setFlash(
        `Deleted: ${res.facts_deleted} facts, ${res.review_items_deleted} review items, ` +
          `${res.registry_entities_deleted} orphaned entities removed` +
          (res.graph_cleaned ? ' (graph cleaned).' : ' (graph cleanup skipped).'),
      )
      queryClient.invalidateQueries({ queryKey: ['evidence-list'] })
      queryClient.invalidateQueries({ queryKey: ['fact-review'] })
    },
    onError: (err, vars) => setRowError({ id: vars.id, message: (err as Error).message }),
  })
  const approve = useMutation({
    mutationFn: (id: number) => api.approveFactReview(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fact-review'] }),
  })
  const reject = useMutation({
    mutationFn: (id: number) => api.rejectFactReview(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fact-review'] }),
  })

  const onDelete = (ev: EvidenceSummary) => {
    const running = ACTIVE.has(ev.status)
    const msg = running
      ? `"${ev.source_name}" is still processing. Force-stop and delete it, along with all its extracted facts?`
      : `Delete "${ev.source_name}" and all its extracted facts? This cannot be undone.`
    if (window.confirm(msg)) {
      deleteEv.mutate({ id: ev.id, force: running })
    }
  }

  const rows = evidenceQuery.data ?? []
  const review = reviewQuery.data ?? []
  const busy = ingestText.isPending

  return (
    <main className="page">
      <div className="container stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
          <h2 style={{ margin: 0 }}>Ingest unstructured data</h2>
          <Link to={`/graphs/${INTEL_GRAPH_ID}`}>Open Intelligence Graph in Explorer →</Link>
        </div>
        <p className="muted" style={{ margin: 0 }}>
          Anything you ingest is parsed, run through LLM extraction, resolved against the
          existing entity registry (so re-ingesting the same people/companies enriches
          them instead of duplicating), written to the graph, and auto-enriched. Every
          stage streams its progress below — you can stop a run or delete an item at any
          time.
        </p>

        <div className="card stack" style={{ maxWidth: 640 }}>
          <h3 style={{ margin: 0 }}>Paste text</h3>
          <input
            placeholder="Source name (e.g. field-report-2026-07-13)"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
          />
          <textarea
            rows={7}
            placeholder="Paste an intelligence report, article, email, transcript…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            disabled={busy || !text.trim()}
            onClick={() => ingestText.mutate()}
          >
            {ingestText.isPending ? 'Ingesting…' : 'Ingest text'}
          </button>
          {ingestText.isError && (
            <p style={{ color: 'var(--color-danger)', margin: 0 }}>
              {(ingestText.error as Error).message}
            </p>
          )}
        </div>

        {flash && <p className="muted" style={{ margin: 0 }}>{flash}</p>}

        {review.length > 0 && (
          <div className="card stack">
            <h3 style={{ margin: 0 }}>Needs review ({review.length})</h3>
            {review.slice(0, 8).map((item) => (
              <div key={item.id} className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                <span style={{ flex: 1 }}>
                  <span className="badge" style={{ marginRight: 8 }}>{item.kind ?? 'fact'}</span>
                  {item.reason}
                </span>
                <span className="row" style={{ gap: 6 }}>
                  <button onClick={() => approve.mutate(item.id)} disabled={approve.isPending}>
                    Approve
                  </button>
                  <button onClick={() => reject.mutate(item.id)} disabled={reject.isPending}>
                    Reject
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="card stack">
          <h3 style={{ margin: 0 }}>Evidence ({rows.length})</h3>
          {rows.length === 0 && <p className="muted" style={{ margin: 0 }}>Nothing ingested yet.</p>}
          {rows.map((ev) => {
            const active = ACTIVE.has(ev.status)
            const stopping = active && ev.cancel_requested
            return (
              <div key={ev.id} className="stack" style={{ gap: 6, borderBottom: '1px solid var(--color-border)', paddingBottom: 8 }}>
                <div className="row" style={{ justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <button
                    className="link-button"
                    style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', font: 'inherit', textAlign: 'left' }}
                    onClick={() => setSelectedId(selectedId === ev.id ? null : ev.id)}
                  >
                    <strong>{ev.source_name}</strong>{' '}
                    <span className="badge">{ev.source_type}</span>
                  </button>
                  <span className="row" style={{ gap: 8 }}>
                    <StatusChip status={ev.status} cancelRequested={ev.cancel_requested} />
                    {active && (
                      <button
                        onClick={() => cancel.mutate(ev.id)}
                        disabled={cancel.isPending || stopping}
                        title="Stop the pipeline at the next stage boundary"
                      >
                        {stopping ? 'Stopping…' : 'Stop'}
                      </button>
                    )}
                    {(ev.status === 'failed' || ev.status === 'cancelled') && (
                      <button onClick={() => retry.mutate(ev.id)} disabled={retry.isPending}>
                        Retry
                      </button>
                    )}
                    {(TERMINAL.has(ev.status) || active) && (
                      <button
                        onClick={() => onDelete(ev)}
                        disabled={deleteEv.isPending}
                        style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}
                        title="Delete this evidence and everything extracted from it"
                      >
                        Delete
                      </button>
                    )}
                  </span>
                </div>
                <PipelineProgress status={ev.status} error={ev.error} />
                {ev.last_log && selectedId !== ev.id && (
                  <p className="muted" style={{ margin: 0, fontSize: '0.85em', fontFamily: 'var(--font-mono, monospace)' }}>
                    {fmtTime(ev.last_log.at)} · {ev.last_log.stage} — {ev.last_log.detail}
                  </p>
                )}
                {rowError?.id === ev.id && (
                  <p style={{ color: 'var(--color-danger)', margin: 0, fontSize: '0.9em' }}>
                    {rowError.message}
                  </p>
                )}
                {selectedId === ev.id && detailQuery.data && (
                  <EvidenceDetailView detail={detailQuery.data} />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </main>
  )
}
