import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { EvidenceDetail, EvidenceSummary } from '../api/types'

const INTEL_GRAPH_ID = 'intelligence_graph'

const STAGES = ['parsed', 'extracted', 'resolved', 'written', 'enriched'] as const
const ACTIVE = new Set(['uploaded', 'queued', 'parsed', 'extracted', 'resolved', 'written'])
const ACCEPT =
  '.pdf,.docx,.txt,.md,.log,.csv,.tsv,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp'

function stageIndex(status: string): number {
  const i = STAGES.indexOf(status as (typeof STAGES)[number])
  return i
}

function StatusChip({ status }: { status: string }) {
  const color =
    status === 'failed'
      ? 'var(--color-danger)'
      : status === 'enriched' || status === 'written'
        ? 'var(--color-success, #2e7d32)'
        : 'var(--color-primary)'
  return (
    <span
      className="badge"
      style={{ borderColor: color, color, display: 'inline-flex', gap: 6, alignItems: 'center' }}
    >
      {ACTIVE.has(status) && <span className="spinner" style={{ width: 10, height: 10 }} />}
      {status}
    </span>
  )
}

function PipelineProgress({ status }: { status: string }) {
  const reached = stageIndex(status)
  return (
    <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
      {STAGES.map((stage, i) => {
        const done = status === 'failed' ? false : reached >= i
        return (
          <span
            key={stage}
            className="badge"
            style={{
              opacity: done ? 1 : 0.35,
              borderColor: done ? 'var(--color-primary)' : 'var(--color-border)',
            }}
          >
            {i + 1}. {stage}
          </span>
        )
      })}
    </div>
  )
}

function FileDrop({ disabled, onFile }: { disabled?: boolean; onFile: (f: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <div
      className="card"
      style={{
        borderStyle: 'dashed',
        borderColor: over ? 'var(--color-primary)' : 'var(--color-border)',
        textAlign: 'center',
        padding: 'var(--space-5)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        const file = e.dataTransfer.files[0]
        if (file && !disabled) onFile(file)
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        style={{ display: 'none' }}
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = ''
        }}
      />
      <p style={{ margin: 0, fontSize: '1.05em' }}>
        Drop a document here, or click to browse
      </p>
      <p className="muted" style={{ margin: 0 }}>
        PDF, DOCX, TXT/MD, CSV, or scanned images (OCR). Duplicates are detected by hash.
      </p>
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
  return (
    <div className="stack" style={{ gap: 'var(--space-3)' }}>
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

      {(detail.processing_log?.length ?? 0) > 0 && (
        <details>
          <summary className="muted">Processing log</summary>
          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
            {detail.processing_log!.map((entry, i) => (
              <li key={i} className="muted">
                <code>{entry.stage}</code> — {entry.detail}
              </li>
            ))}
          </ul>
        </details>
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
  const ingestFile = useMutation({
    mutationFn: (file: File) => api.ingestFile(file),
    onSuccess: (res) => afterIngest(res.evidence_id, res.note),
  })
  const retry = useMutation({
    mutationFn: (id: string) => api.retryEvidence(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['evidence-list'] }),
  })
  const approve = useMutation({
    mutationFn: (id: number) => api.approveFactReview(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fact-review'] }),
  })
  const reject = useMutation({
    mutationFn: (id: number) => api.rejectFactReview(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fact-review'] }),
  })

  const rows = evidenceQuery.data ?? []
  const review = reviewQuery.data ?? []
  const busy = ingestText.isPending || ingestFile.isPending

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
          them instead of duplicating), written to the graph, and auto-enriched.
        </p>

        <div className="row" style={{ alignItems: 'stretch', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div className="card stack" style={{ flex: '1 1 340px' }}>
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

          <div className="card stack" style={{ flex: '1 1 340px' }}>
            <h3 style={{ margin: 0 }}>Upload a document</h3>
            <FileDrop disabled={busy} onFile={(file) => ingestFile.mutate(file)} />
            {ingestFile.isError && (
              <p style={{ color: 'var(--color-danger)', margin: 0 }}>
                {(ingestFile.error as Error).message}
              </p>
            )}
          </div>
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
          {rows.map((ev) => (
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
                  <StatusChip status={ev.status} />
                  {ev.status === 'failed' && (
                    <button onClick={() => retry.mutate(ev.id)} disabled={retry.isPending}>
                      Retry
                    </button>
                  )}
                </span>
              </div>
              <PipelineProgress status={ev.status} />
              {selectedId === ev.id && detailQuery.data && (
                <EvidenceDetailView detail={detailQuery.data} />
              )}
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
