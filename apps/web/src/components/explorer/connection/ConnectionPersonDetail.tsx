import type { PersonNode, RiskResult } from '../../../api/types'
import PropertiesList from '../../common/PropertiesList'
import DetailShell, { type DetailTab } from '../detail/DetailShell'
import ReasonCard from '../detail/ReasonCard'
import { Callout, ConfidenceMeter, CopyValue, FieldRow, PersonRow, Section } from '../detail/parts'
import {
  confidenceLabel,
  confidenceTone,
  describeLink,
  factProperties,
  otherEnd,
  riskColor,
  type DetailActions,
  type DetailData,
} from '../detail/detailModel'
import { colorForDegree, colorForTag, ROOT_COLOR } from '../graphStyle'

/** Where a person sits on the chain. Defined here rather than beside the
 * graph, because the position only ever changes what this panel *says*
 * about someone — the canvas colours them by degree, like everywhere else. */
export type PathRole = 'source' | 'target' | 'hop'

interface Props {
  person: PersonNode
  role: PathRole
  /** 1-based position along the chain, and how long the chain is — the two
   * numbers that place this person in the answer. */
  step: number
  chainLength: number
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  onExplore: (personId: string) => void
}

const ROLE_TEXT: Record<PathRole, string> = {
  source: 'The person the search started from',
  target: 'The person the search was looking for',
  hop: 'An intermediate link in the chain',
}

/** One person on the connection path.
 *
 * Deliberately not Explore's `PersonDetail`: that view is about a person's
 * place on the canvas — which of their details are fanned out, whether
 * they're expanded — and none of that exists here. What matters on this
 * screen is where they sit in the chain and which hops run through them. */
export default function ConnectionPersonDetail({
  person,
  role,
  step,
  chainLength,
  data,
  actions,
  risk,
  onExplore,
}: Props) {
  const links = [...(data.linksByPerson.get(person.id) ?? [])].sort(
    (a, b) => b.confidence - a.confidence,
  )
  const ownRisk = risk && risk.entity_id === person.id ? risk : null
  const accent = role === 'source' ? ROOT_COLOR : (colorForDegree(person.degree) ?? ROOT_COLOR)

  const overview = (
    <>
      <Section title="Position in this chain">
        <Callout>{ROLE_TEXT[role]}.</Callout>
        <div style={{ marginTop: 'var(--space-3)' }}>
          <FieldRow label="Step" value={`${step} of ${chainLength}`} />
          <FieldRow
            label="Distance"
            value={
              person.degree === 0
                ? 'The person searched from'
                : `${person.degree} step${person.degree === 1 ? '' : 's'} from the source`
            }
          />
          <FieldRow label="Hops through this person" value={links.length} />
        </div>
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
        <Callout>No hop on this chain runs through this person.</Callout>
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
              <div style={{ marginTop: 'var(--space-2)' }}>
                <ConfidenceMeter value={link.confidence} label="This hop" />
              </div>
              <div className="connection-card__reasons">
                {reasons.map((reason, i) => (
                  <ReasonCard
                    key={i}
                    descriptor={reason}
                    labelFor={actions.labelFor}
                    onOpen={actions.openVid}
                  />
                ))}
              </div>
            </div>
          )
        })
      )}
    </>
  )

  const riskTab = ownRisk ? (
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
    { id: 'connections', label: 'Hops', count: links.length, content: connections },
    { id: 'risk', label: 'Risk', content: riskTab },
    { id: 'raw', label: 'Raw', content: raw },
  ]

  return (
    <DetailShell
      kind="Person"
      accent={accent}
      title={person.label}
      subtitle={<CopyValue value={person.id} />}
      chips={
        <>
          <span className="tag-chip">
            <span className="tag-dot" style={{ background: colorForTag('person') }} />
            {person.entity_type}
          </span>
          <span className="tag-chip">
            step {step} of {chainLength}
          </span>
        </>
      }
      actions={
        <>
          <button className="btn btn--primary btn-sm" onClick={() => onExplore(person.id)}>
            Explore this person
          </button>
          <button className="btn btn-sm" onClick={() => actions.fetchRisk(person.id)}>
            Risk
          </button>
        </>
      }
      onClose={() => actions.select(null)}
      tabs={tabs}
    />
  )
}
