import type { PersonNode, RiskResult } from '../../../api/types'
import PropertiesList from '../../common/PropertiesList'
import InfoTooltip from '../../common/InfoTooltip'
import { attributeNodeLabel } from '../attributeLabel'
import { colorForDegree, colorForTag } from '../graphStyle'
import DetailShell, { type DetailTab } from './DetailShell'
import ReasonCard from './ReasonCard'
import { Callout, CopyValue, EntityRow, FieldRow, PersonRow, Section } from './parts'
import {
  confidenceLabel,
  confidenceTone,
  degreeText,
  describeLink,
  factProperties,
  groupAttributesByTag,
  otherEnd,
  riskColor,
  type DetailActions,
  type DetailData,
} from './detailModel'

interface Props {
  person: PersonNode
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  pathSource: string | null
  isRoot: boolean
}

/** Everything known about one person, in the order an investigator asks for
 * it: who they are, who they're connected to and why, what's on record, what
 * the risk model makes of them. */
export default function PersonDetail({ person, data, actions, risk, pathSource, isRoot }: Props) {
  const links = [...(data.linksByPerson.get(person.id) ?? [])].sort(
    (a, b) => b.confidence - a.confidence,
  )
  const attributes = data.attributes.get(person.id) ?? []
  const isLoadingAttributes = data.loadingAttributes.has(person.id)
  const strongest = links[0]
  const ownRisk = risk && risk.entity_id === person.id ? risk : null

  const overview = (
    <>
      <Section title="Position in this network">
        <FieldRow label="Distance" value={degreeText(person.degree, data.rootLabel)} />
        <FieldRow label="Connected people" value={links.length} />
        {strongest && (
          <FieldRow
            label="Strongest link"
            value={`${data.personsById.get(otherEnd(strongest, person.id))?.label ?? '—'} · ${confidenceLabel(
              strongest.confidence,
            )}`}
          />
        )}
        <FieldRow
          label="Details on record"
          value={isLoadingAttributes && attributes.length === 0 ? 'Loading…' : attributes.length}
        />
        <FieldRow label="Shown on canvas" value={data.expanded.has(person.id) ? 'Details open' : 'Collapsed'} />
      </Section>

      <Section title="Identity">
        <PropertiesList
          properties={factProperties(person.properties)}
          emptyLabel="No identity fields recorded."
        />
      </Section>
    </>
  )

  const connections = (
    <>
      {links.length === 0 ? (
        <Callout>
          Nothing links this person to anyone else at the current degree and confidence. Widen
          either control to look further out.
        </Callout>
      ) : (
        links.map((link) => {
          const otherId = otherEnd(link, person.id)
          const reasons = describeLink(link, data.attributesById, data.personsById)
          return (
            <div className="connection-card" key={`${link.source}|${link.target}`}>
              <PersonRow
                person={data.personsById.get(otherId)}
                fallbackId={otherId}
                onSelect={actions.openVid}
                right={
                  <span className={`meter__value meter__value--${confidenceTone(link.confidence)}`}>
                    {confidenceLabel(link.confidence)}
                  </span>
                }
              />
              <div className="connection-card__reasons">
                {reasons.map((reason, i) => (
                  <ReasonCard key={i} descriptor={reason} labelFor={actions.labelFor} onOpen={actions.openVid} />
                ))}
              </div>
            </div>
          )
        })
      )}
    </>
  )

  const details = (
    <>
      {attributes.length === 0 ? (
        <Callout>
          {isLoadingAttributes
            ? 'Loading this person’s details…'
            : 'No documents or contact details on record for this person.'}
        </Callout>
      ) : (
        groupAttributesByTag(attributes).map(([tag, list]) => (
          <Section key={tag} title={tag.replace(/_/g, ' ')} count={list.length}>
            {list.map((attribute) => {
              const title = attributeNodeLabel(attribute)
              return (
                <EntityRow
                  key={attribute.id}
                  label={title}
                  meta={title === attribute.label ? undefined : attribute.label}
                  accent={colorForTag(attribute.tag)}
                  onSelect={() => actions.select({ kind: 'attribute', id: attribute.id })}
                  right={
                    attribute.shared_with.length > 0 ? (
                      <span className="badge badge--warn">
                        shared ×{attribute.shared_with.length + 1}
                      </span>
                    ) : undefined
                  }
                />
              )
            })}
          </Section>
        ))
      )}
    </>
  )

  const riskTab = (
    <>
      {ownRisk ? (
        <>
          <Section title="Score">
            <div className="risk-badge" style={{ background: riskColor(ownRisk.level), color: '#fff' }}>
              {ownRisk.level.toUpperCase()} · {ownRisk.score.toFixed(2)}
            </div>
          </Section>
          <Section title="Contributing factors" count={ownRisk.factors.length}>
            {ownRisk.factors.length === 0 ? (
              <Callout>No individual factors fired — the score is the baseline.</Callout>
            ) : (
              ownRisk.factors.map((factor, i) => (
                <div className="reason-card" key={i}>
                  <div className="reason-card__head">
                    <span className="reason-card__kind">{factor.code.replace(/_/g, ' ')}</span>
                    <span className="badge">weight {factor.weight}</span>
                  </div>
                  <p className="reason-card__detail">{factor.explanation}</p>
                </div>
              ))
            )}
          </Section>
        </>
      ) : (
        <Callout>
          No risk assessment loaded for this person yet.
          <div style={{ marginTop: 'var(--space-3)' }}>
            <button className="btn btn-sm" onClick={() => actions.fetchRisk(person.id)}>
              Calculate risk
            </button>
          </div>
        </Callout>
      )}
    </>
  )

  const raw = (
    <>
      <Section title="Identifier">
        <CopyValue value={person.id} />
      </Section>
      <Section title="All properties">
        <PropertiesList properties={person.properties} />
      </Section>
    </>
  )

  const tabs: DetailTab[] = [
    { id: 'overview', label: 'Overview', content: overview },
    { id: 'connections', label: 'Connections', count: links.length, content: connections },
    { id: 'details', label: 'Details', count: attributes.length, content: details },
    { id: 'risk', label: 'Risk', content: riskTab },
    { id: 'raw', label: 'Raw', content: raw },
  ]

  const isPathSource = pathSource === person.id

  return (
    <DetailShell
      kind="Person"
      accent={colorForDegree(person.degree) ?? colorForTag('person')}
      title={person.label}
      subtitle={<CopyValue value={person.id} />}
      chips={
        <>
          <span className="tag-chip">
            <span className="tag-dot" style={{ background: colorForTag('person') }} />
            {person.entity_type}
          </span>
          <span className="tag-chip">{isRoot ? 'searched person' : `${person.degree}° away`}</span>
          {isPathSource && <span className="tag-chip tag-chip--active">path start</span>}
        </>
      }
      actions={
        <>
          <button
            className="btn btn--primary btn-sm"
            onClick={() => actions.toggleExpand(person.id)}
            disabled={isLoadingAttributes}
          >
            {isLoadingAttributes
              ? 'Loading…'
              : data.expanded.has(person.id)
                ? 'Hide on canvas'
                : 'Show on canvas'}
          </button>
          <InfoTooltip text="Fan this person's own details (phone, email, address, passport, ...) out in a ring around them on the canvas." />
          <button className="btn btn-sm" onClick={() => actions.fetchRisk(person.id)}>
            Risk
          </button>
          {pathSource && pathSource !== person.id ? (
            <button className="btn btn-sm" onClick={() => actions.runPath(person.id)}>
              Path to here
            </button>
          ) : (
            <button
              className="btn btn-sm"
              onClick={() => actions.setPathSource(isPathSource ? null : person.id)}
            >
              {isPathSource ? 'Cancel path' : 'Path from here'}
            </button>
          )}
          <InfoTooltip text="Find the shortest chain of connections between two people. Set a start here, then open another person and pick 'Path to here'." />
        </>
      }
      onClose={() => actions.select(null)}
      tabs={tabs}
    />
  )
}
