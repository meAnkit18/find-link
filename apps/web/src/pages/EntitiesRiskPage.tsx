import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import Field from '../components/common/Field'
import GraphPicker from '../components/common/GraphPicker'
import RunResult from '../components/common/RunResult'
import InfoTooltip from '../components/common/InfoTooltip'

/** Entities & risk workbench: entity search, fetch, graph expansion,
 * shortest path, risk scoring, and risk explanation — covers every
 * /api/graphs/{id}/entities/* endpoint plus /api/risk/*. */
export default function EntitiesRiskPage() {
  const [graphId, setGraphId] = useState('')

  // Entity search
  const [entityType, setEntityType] = useState('person')
  const [searchQ, setSearchQ] = useState('')
  const searchEntities = useMutation({
    mutationFn: () => api.searchEntities(graphId, searchQ, entityType.trim() || 'person'),
  })

  // Entity fetch / expand
  const [entityId, setEntityId] = useState('')
  const [depth, setDepth] = useState('1')
  const getEntity = useMutation({ mutationFn: () => api.getEntity(graphId, entityId.trim()) })
  const expandGraph = useMutation({
    mutationFn: () => api.expandEntityGraph(graphId, entityId.trim(), Number(depth) || 1),
  })

  // Risk (per-entity, entities router)
  const entityRisk = useMutation({ mutationFn: () => api.getEntityRisk(graphId, entityId.trim()) })
  const entityRiskExplain = useMutation({
    mutationFn: () => api.explainEntityRisk(graphId, entityId.trim()),
  })

  // Risk (default-graph /api/risk router)
  const [riskEntityId, setRiskEntityId] = useState('')
  const globalRisk = useMutation({ mutationFn: () => api.calculateRisk(riskEntityId.trim()) })
  const globalRiskExplain = useMutation({ mutationFn: () => api.explainRisk(riskEntityId.trim()) })

  // Shortest path
  const [source, setSource] = useState('')
  const [target, setTarget] = useState('')
  const [maxSteps, setMaxSteps] = useState('5')
  const shortestPath = useMutation({
    mutationFn: () => api.shortestPath(graphId, source.trim(), target.trim(), Number(maxSteps) || 5),
  })

  const needsGraph = !graphId

  return (
    <main className="page">
      <div className="container stack">
        <h2 className="page-title">Entities &amp; risk</h2>
        <p className="muted">
          Note: the entities/risk services are bound to the backend's default
          space (<code className="mono">intelligence_graph</code>); the graph
          picked below only satisfies the URL path.
        </p>

        <section className="card stack">
          <GraphPicker
            value={graphId}
            onChange={setGraphId}
            info="Only sets which graph the URL points to — see the note above."
          />
        </section>

        <section className="card stack">
          <h3>Search entities</h3>
          <div className="form-grid">
            <Field
              label="Entity type (tag)"
              value={entityType}
              onChange={setEntityType}
              placeholder="person"
              info="What kind of thing to search for, e.g. person, company, or address."
            />
            <Field
              label="Query"
              value={searchQ}
              onChange={setSearchQ}
              placeholder="substring of label"
              info="Part of the name to search for — doesn't need to be exact."
            />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={needsGraph || searchEntities.isPending}
              onClick={() => searchEntities.mutate()}
            >
              {searchEntities.isPending && <span className="spinner" />} Search
            </button>
          </div>
          <RunResult mutation={searchEntities} title="GET …/entities/search" />
        </section>

        <section className="card stack">
          <h3>Entity lookup, expansion &amp; risk</h3>
          <div className="form-grid">
            <Field
              label="Entity ID (vid)"
              value={entityId}
              onChange={setEntityId}
              placeholder="e.g. person:abc123"
              info="The unique ID of the person or company, shown on their node detail panel in the graph explorer."
            />
            <Field
              label="Expansion depth (1–5)"
              value={depth}
              onChange={setDepth}
              type="number"
              info="How many steps out from this entity to fetch when expanding the graph."
            />
          </div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <button className="btn" disabled={needsGraph || !entityId.trim()} onClick={() => getEntity.mutate()}>
              Get entity
            </button>
            <InfoTooltip text="Fetch this entity's stored details." />
            <button className="btn" disabled={needsGraph || !entityId.trim()} onClick={() => expandGraph.mutate()}>
              Expand graph
            </button>
            <InfoTooltip text="Fetch everyone and everything directly connected to this entity." />
            <button className="btn" disabled={needsGraph || !entityId.trim()} onClick={() => entityRisk.mutate()}>
              Calculate risk
            </button>
            <InfoTooltip text="Score how risky this entity is, based on its connections and known flags." />
            <button
              className="btn"
              disabled={needsGraph || !entityId.trim()}
              onClick={() => entityRiskExplain.mutate()}
            >
              Explain risk
            </button>
            <InfoTooltip text="Show the specific reasons behind this entity's risk score." />
          </div>
          <RunResult mutation={getEntity} title="GET …/entities/{entity_id}" />
          <RunResult mutation={expandGraph} title="GET …/entities/{entity_id}/graph" />
          <RunResult mutation={entityRisk} title="GET …/entities/{entity_id}/risk" />
          <RunResult mutation={entityRiskExplain} title="GET …/entities/{entity_id}/risk/explain" />
        </section>

        <section className="card stack">
          <h3>
            Shortest path between two entities
            <InfoTooltip text="Finds the shortest chain of connections linking two people or companies." />
          </h3>
          <div className="form-grid">
            <Field label="Source vid" value={source} onChange={setSource} info="The starting entity's ID." />
            <Field label="Target vid" value={target} onChange={setTarget} info="The destination entity's ID." />
            <Field
              label="Max steps (1–10)"
              value={maxSteps}
              onChange={setMaxSteps}
              type="number"
              info="The longest chain of connections to search before giving up."
            />
          </div>
          <div className="row">
            <button
              className="btn btn--primary"
              disabled={needsGraph || !source.trim() || !target.trim() || shortestPath.isPending}
              onClick={() => shortestPath.mutate()}
            >
              {shortestPath.isPending && <span className="spinner" />} Find path
            </button>
          </div>
          <RunResult mutation={shortestPath} title="GET …/entities/shortest-path" />
        </section>

        <section className="card stack">
          <h3>
            Global risk endpoints (/api/risk)
            <InfoTooltip text="Same risk scoring as above, but always against the default graph regardless of what's picked at the top of this page." />
          </h3>
          <div className="form-grid">
            <Field
              label="Entity ID"
              value={riskEntityId}
              onChange={setRiskEntityId}
              info="The unique ID of the person or company to score."
            />
          </div>
          <div className="row">
            <button className="btn" disabled={!riskEntityId.trim()} onClick={() => globalRisk.mutate()}>
              GET /api/risk/{'{id}'}
            </button>
            <InfoTooltip text="Score how risky this entity is." />
            <button className="btn" disabled={!riskEntityId.trim()} onClick={() => globalRiskExplain.mutate()}>
              GET /api/risk/{'{id}'}/explain
            </button>
            <InfoTooltip text="Show the specific reasons behind this entity's risk score." />
          </div>
          <RunResult mutation={globalRisk} title="GET /api/risk/{entity_id}" />
          <RunResult mutation={globalRiskExplain} title="GET /api/risk/{entity_id}/explain" />
        </section>
      </div>
    </main>
  )
}
