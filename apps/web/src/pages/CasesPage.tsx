import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import Field from '../components/common/Field'
import JsonView from '../components/common/JsonView'
import RunResult from '../components/common/RunResult'
import InfoTooltip from '../components/common/InfoTooltip'

/** Investigation cases workbench: create / list / inspect cases, attach
 * subjects, and add notes — covers every /api/cases endpoint. */
export default function CasesPage() {
  const queryClient = useQueryClient()

  // Create case
  const [title, setTitle] = useState('')
  const [createdBy, setCreatedBy] = useState('tester')
  const [priority, setPriority] = useState('medium')

  // Selected case + sub-forms
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [subjectEntityId, setSubjectEntityId] = useState('')
  const [subjectRole, setSubjectRole] = useState('primary')
  const [noteBody, setNoteBody] = useState('')

  const casesQuery = useQuery({ queryKey: ['cases'], queryFn: api.listCases })

  const createCase = useMutation({
    mutationFn: () => api.createCase(title.trim(), createdBy.trim(), priority),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      setSelectedCaseId(created.case_id)
      setTitle('')
    },
  })

  const caseDetailQuery = useQuery({
    queryKey: ['case', selectedCaseId],
    queryFn: () => api.getCase(selectedCaseId),
    enabled: Boolean(selectedCaseId),
  })

  const addSubject = useMutation({
    mutationFn: () =>
      api.addCaseSubject(selectedCaseId, subjectEntityId.trim(), subjectRole.trim(), createdBy.trim()),
  })

  const addNote = useMutation({
    mutationFn: () => api.addCaseNote(selectedCaseId, noteBody.trim(), createdBy.trim()),
    onSuccess: () => setNoteBody(''),
  })

  return (
    <main className="page">
      <div className="container stack">
        <h2 className="page-title">Investigation cases</h2>

        <section className="card stack">
          <h3>Create a case</h3>
          <div className="form-grid">
            <Field
              label="Title"
              value={title}
              onChange={setTitle}
              placeholder="e.g. Suspicious vendor ring"
              info="A short name for this investigation, so you can find it again later."
            />
            <Field
              label="Created by"
              value={createdBy}
              onChange={setCreatedBy}
              info="Your name or username, recorded as the case owner."
            />
            <label className="field">
              <span className="field__label">
                Priority
                <InfoTooltip text="How urgent this case is. Doesn't change what you can do — just helps sort the case list." />
              </span>
              <select className="select" value={priority} onChange={(e) => setPriority(e.target.value)}>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
              </select>
            </label>
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={!title.trim() || !createdBy.trim() || createCase.isPending}
              onClick={() => createCase.mutate()}
            >
              {createCase.isPending && <span className="spinner" />} Create case
            </button>
          </div>
          <RunResult mutation={createCase} title="POST /api/cases" />
        </section>

        <section className="card stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h3>All cases</h3>
            <button className="btn" onClick={() => casesQuery.refetch()}>
              Refresh
            </button>
          </div>
          {casesQuery.isLoading && <p className="muted">Loading…</p>}
          {casesQuery.isError && <p className="error-text">✗ {(casesQuery.error as Error).message}</p>}
          {casesQuery.data?.length === 0 && <p className="muted">No cases yet — create one above.</p>}
          <div className="stack" style={{ gap: 'var(--space-2)' }}>
            {casesQuery.data?.map((c) => (
              <button
                key={c.case_id}
                className={`list-item ${selectedCaseId === c.case_id ? 'list-item--active' : ''}`}
                onClick={() => setSelectedCaseId(c.case_id)}
              >
                <strong>{String(c.title ?? '(untitled)')}</strong>
                <span className="muted"> · {String(c.status ?? '?')} · {String(c.priority ?? '?')}</span>
                <div className="mono muted">{c.case_id}</div>
              </button>
            ))}
          </div>
        </section>

        {selectedCaseId && (
          <section className="card stack">
            <h3>
              Selected case <code className="mono">{selectedCaseId}</code>
              <InfoTooltip text="A unique ID for this case, generated automatically." />
            </h3>

            {caseDetailQuery.isLoading && <p className="muted">Loading…</p>}
            {caseDetailQuery.isError && (
              <p className="error-text">✗ {(caseDetailQuery.error as Error).message}</p>
            )}
            {caseDetailQuery.data !== undefined && (
              <JsonView data={caseDetailQuery.data} title="GET /api/cases/{case_id}" />
            )}

            <h4>
              Add subject
              <InfoTooltip text="A subject is a person or company this case is about. Attach them here so they show up in the case file." />
            </h4>
            <div className="form-grid">
              <Field
                label="Entity ID"
                value={subjectEntityId}
                onChange={setSubjectEntityId}
                placeholder="vid of an entity in the graph"
                info="The unique ID of the person or company in the graph, shown on their node detail panel."
              />
              <Field
                label="Role"
                value={subjectRole}
                onChange={setSubjectRole}
                placeholder="primary / associate…"
                info="How this subject relates to the case, e.g. primary suspect or associate."
              />
            </div>
            <div className="row">
              <button
                className="btn btn--primary"
                disabled={!subjectEntityId.trim() || addSubject.isPending}
                onClick={() => addSubject.mutate()}
              >
                {addSubject.isPending && <span className="spinner" />} Add subject
              </button>
            </div>
            <RunResult mutation={addSubject} title="POST /api/cases/{case_id}/subjects" />

            <h4>Add note</h4>
            <label className="field">
              <span className="field__label">
                Note body
                <InfoTooltip text="Free-text notes about this case, saved with a timestamp for the case record." />
              </span>
              <textarea
                className="input"
                rows={3}
                value={noteBody}
                onChange={(e) => setNoteBody(e.target.value)}
                placeholder="Observations, findings, next steps…"
              />
            </label>
            <div className="row">
              <button
                className="btn btn--primary"
                disabled={!noteBody.trim() || addNote.isPending}
                onClick={() => addNote.mutate()}
              >
                {addNote.isPending && <span className="spinner" />} Add note
              </button>
            </div>
            <RunResult mutation={addNote} title="POST /api/cases/{case_id}/notes" />
          </section>
        )}
      </div>
    </main>
  )
}
