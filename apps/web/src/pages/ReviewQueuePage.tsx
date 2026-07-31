import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import Field from '../components/common/Field'
import JsonView from '../components/common/JsonView'
import RunResult from '../components/common/RunResult'
import GraphPicker from '../components/common/GraphPicker'
import InfoTooltip from '../components/common/InfoTooltip'

/** Review queue workbench: list pending items (optionally by queue type)
 * and approve/reject them — covers every /api/review-queue endpoint. */
export default function ReviewQueuePage() {
  const queryClient = useQueryClient()
  const [graphId, setGraphId] = useState('')
  const [queueType, setQueueType] = useState('')
  const [reviewedBy, setReviewedBy] = useState('tester')
  const [reason, setReason] = useState('')
  const [selectedReviewId, setSelectedReviewId] = useState('')

  const itemsQuery = useQuery({
    queryKey: ['review-items', graphId, queueType],
    queryFn: () => api.listReviewItems(graphId, queueType.trim() || undefined),
    enabled: Boolean(graphId),
  })

  const approve = useMutation({
    mutationFn: () =>
      api.approveReview(graphId, selectedReviewId, reviewedBy.trim(), reason.trim() || undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['review-items'] }),
  })

  const reject = useMutation({
    mutationFn: () => api.rejectReview(graphId, selectedReviewId, reviewedBy.trim(), reason.trim()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['review-items'] }),
  })

  return (
    <main className="page">
      <div className="container stack">
        <h2 className="page-title">
          Review queue
          <InfoTooltip text="Items the system flagged as needing a human decision before they're applied — e.g. merging two records that might be the same person." />
        </h2>

        <section className="card stack">
          <div className="form-grid">
            <GraphPicker value={graphId} onChange={setGraphId} info="Which graph to list pending review items for." />
            <Field
              label="Queue type filter (optional)"
              value={queueType}
              onChange={setQueueType}
              placeholder="e.g. entity_merge"
              info="Show only one kind of review item. Leave blank to see everything."
            />
          </div>
          <div className="row">
            <button className="btn" disabled={!graphId} onClick={() => itemsQuery.refetch()}>
              Refresh list
            </button>
          </div>

          {itemsQuery.isLoading && <p className="muted">Loading…</p>}
          {itemsQuery.isError && <p className="error-text">✗ {(itemsQuery.error as Error).message}</p>}
          {itemsQuery.data?.length === 0 && (
            <p className="muted">No pending review items in this graph.</p>
          )}
          {itemsQuery.data && itemsQuery.data.length > 0 && (
            <>
              <div className="stack" style={{ gap: 'var(--space-2)' }}>
                {itemsQuery.data.map((item) => (
                  <button
                    key={item.review_id}
                    className={`list-item ${selectedReviewId === item.review_id ? 'list-item--active' : ''}`}
                    onClick={() => setSelectedReviewId(item.review_id)}
                  >
                    <strong className="mono">{item.review_id}</strong>
                    <span className="muted">
                      {' '}· {String(item.queue_type ?? '?')} · {String(item.status ?? '?')}
                    </span>
                  </button>
                ))}
              </div>
              <JsonView data={itemsQuery.data} title="GET /api/review-queue" initiallyOpen={false} />
            </>
          )}
        </section>

        {selectedReviewId && (
          <section className="card stack">
            <h3>
              Decide <code className="mono">{selectedReviewId}</code>
            </h3>
            <div className="form-grid">
              <Field
                label="Reviewed by"
                value={reviewedBy}
                onChange={setReviewedBy}
                info="Your name or username, recorded against this decision."
              />
              <Field
                label="Reason (required to reject)"
                value={reason}
                onChange={setReason}
                placeholder="why approving / rejecting"
                info="A short note explaining your decision, kept for the record."
              />
            </div>
            <div className="row">
              <button
                className="btn btn--primary"
                disabled={!reviewedBy.trim() || approve.isPending}
                onClick={() => approve.mutate()}
              >
                {approve.isPending && <span className="spinner" />} Approve
              </button>
              <button
                className="btn btn--danger"
                disabled={!reviewedBy.trim() || !reason.trim() || reject.isPending}
                onClick={() => reject.mutate()}
              >
                {reject.isPending && <span className="spinner" />} Reject
              </button>
            </div>
            <RunResult mutation={approve} title="POST …/approve" />
            <RunResult mutation={reject} title="POST …/reject" />
          </section>
        )}
      </div>
    </main>
  )
}
