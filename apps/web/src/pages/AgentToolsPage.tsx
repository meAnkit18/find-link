import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import Field from '../components/common/Field'
import RunResult from '../components/common/RunResult'
import InfoTooltip from '../components/common/InfoTooltip'

/** Agent toolbox workbench — one form per /api/agent/* tool. */
export default function AgentToolsPage() {
  const [personQuery, setPersonQuery] = useState('')
  const searchPerson = useMutation({ mutationFn: () => api.agentSearchPerson(personQuery.trim()) })

  const [expandId, setExpandId] = useState('')
  const [expandDepth, setExpandDepth] = useState('1')
  const expandNode = useMutation({
    mutationFn: () => api.agentExpandNode(expandId.trim(), Number(expandDepth) || 1),
  })

  const [pathSource, setPathSource] = useState('')
  const [pathTarget, setPathTarget] = useState('')
  const shortestPath = useMutation({
    mutationFn: () => api.agentShortestPath(pathSource.trim(), pathTarget.trim()),
  })

  const [mergeSource, setMergeSource] = useState('')
  const [mergeTarget, setMergeTarget] = useState('')
  const mergeEntities = useMutation({
    mutationFn: () => api.agentMergeEntities(mergeSource.trim(), mergeTarget.trim()),
  })

  const [riskId, setRiskId] = useState('')
  const calcRisk = useMutation({ mutationFn: () => api.agentCalculateRisk(riskId.trim()) })

  return (
    <main className="page">
      <div className="container stack">
        <h2 className="page-title">Agent tools</h2>
        <p className="muted">
          The same toolbox the AI agent uses, exposed as forms. All calls run
          against the default <code className="mono">intelligence_graph</code> space.
        </p>

        <section className="card stack">
          <h3>
            search-person
            <InfoTooltip text="Looks up people by (partial) name." />
          </h3>
          <div className="form-grid">
            <Field
              label="Query"
              value={personQuery}
              onChange={setPersonQuery}
              placeholder="name substring"
              info="Part of the person's name to search for."
            />
          </div>
          <div className="row">
            <button className="btn btn--primary" disabled={searchPerson.isPending} onClick={() => searchPerson.mutate()}>
              {searchPerson.isPending && <span className="spinner" />} Run
            </button>
          </div>
          <RunResult mutation={searchPerson} title="POST /api/agent/search-person" />
        </section>

        <section className="card stack">
          <h3>
            expand-node
            <InfoTooltip text="Loads everyone and everything directly connected to a person or company." />
          </h3>
          <div className="form-grid">
            <Field
              label="Entity ID"
              value={expandId}
              onChange={setExpandId}
              info="The unique ID of the person or company to expand."
            />
            <Field
              label="Depth"
              value={expandDepth}
              onChange={setExpandDepth}
              type="number"
              info="How many steps out from this entity to load."
            />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={!expandId.trim() || expandNode.isPending}
              onClick={() => expandNode.mutate()}
            >
              {expandNode.isPending && <span className="spinner" />} Run
            </button>
          </div>
          <RunResult mutation={expandNode} title="POST /api/agent/expand-node" />
        </section>

        <section className="card stack">
          <h3>
            shortest-path
            <InfoTooltip text="Finds the shortest chain of connections between two people or companies." />
          </h3>
          <div className="form-grid">
            <Field label="Source ID" value={pathSource} onChange={setPathSource} info="The starting entity's ID." />
            <Field label="Target ID" value={pathTarget} onChange={setPathTarget} info="The destination entity's ID." />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={!pathSource.trim() || !pathTarget.trim() || shortestPath.isPending}
              onClick={() => shortestPath.mutate()}
            >
              {shortestPath.isPending && <span className="spinner" />} Run
            </button>
          </div>
          <RunResult mutation={shortestPath} title="POST /api/agent/shortest-path" />
        </section>

        <section className="card stack">
          <h3>
            merge-entities
            <InfoTooltip text="Combines two records that represent the same real person or company into one. This cannot be undone." />
          </h3>
          <div className="form-grid">
            <Field
              label="Source entity ID"
              value={mergeSource}
              onChange={setMergeSource}
              info="The duplicate record — it will be merged into the target and no longer exist on its own."
            />
            <Field
              label="Target entity ID"
              value={mergeTarget}
              onChange={setMergeTarget}
              info="The record that survives the merge."
            />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={!mergeSource.trim() || !mergeTarget.trim() || mergeEntities.isPending}
              onClick={() => mergeEntities.mutate()}
            >
              {mergeEntities.isPending && <span className="spinner" />} Run
            </button>
          </div>
          <RunResult mutation={mergeEntities} title="POST /api/agent/merge-entities" />
        </section>

        <section className="card stack">
          <h3>
            calculate-risk
            <InfoTooltip text="Scores how risky a person or company is, based on their connections and known flags." />
          </h3>
          <div className="form-grid">
            <Field label="Entity ID" value={riskId} onChange={setRiskId} info="The unique ID of the person or company to score." />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={!riskId.trim() || calcRisk.isPending}
              onClick={() => calcRisk.mutate()}
            >
              {calcRisk.isPending && <span className="spinner" />} Run
            </button>
          </div>
          <RunResult mutation={calcRisk} title="POST /api/agent/calculate-risk" />
        </section>
      </div>
    </main>
  )
}
