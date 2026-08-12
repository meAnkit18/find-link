import type { ConnectionResult, PersonNode, RiskResult } from '../../../api/types'
import DetailShell, { type DetailTab } from '../detail/DetailShell'
import LinkDetail from '../detail/LinkDetail'
import ReasonCard from '../detail/ReasonCard'
import { Callout, ConfidenceMeter, EntityRow, FieldRow, PersonRow, Section } from '../detail/parts'
import {
  confidenceLabel,
  confidenceTone,
  describeLink,
  selectionKey,
  type DetailActions,
  type DetailData,
  type Selection,
} from '../detail/detailModel'
import { ROOT_COLOR } from '../graphStyle'
import ConnectionPersonDetail, { type PathRole } from './ConnectionPersonDetail'

interface Props {
  result: ConnectionResult
  sourceLabel: string
  targetLabel: string
  selection: Selection | null
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
  onExplore: (personId: string) => void
}

function roleFor(index: number, count: number): PathRole {
  if (index === 0) return 'source'
  if (index === count - 1) return 'target'
  return 'hop'
}

/** The right-hand column in Verify connection mode — the same panel
 * contract Explore uses, over the connection result instead of the canvas
 * projection.
 *
 * A hop reuses Explore's `LinkDetail` outright: "what do these two people
 * actually share, and how sure are we" is the same question there as here,
 * and answering it twice in two places would let the two answers drift. */
export default function ConnectionDetailPanel({
  result,
  sourceLabel,
  targetLabel,
  selection,
  data,
  actions,
  risk,
  onExplore,
}: Props) {
  const key = selectionKey(selection)
  const persons = result.connected ? result.path.persons : []

  if (selection?.kind === 'person') {
    const index = persons.findIndex((p) => p.id === selection.id)
    const person = index >= 0 ? persons[index] : undefined
    if (person) {
      return (
        <ConnectionPersonDetail
          key={key}
          person={person}
          role={roleFor(index, persons.length)}
          step={index + 1}
          chainLength={persons.length}
          data={data}
          actions={actions}
          risk={risk}
          onExplore={onExplore}
        />
      )
    }
  }

  if (selection?.kind === 'link') {
    const link = data.links.find(
      (candidate) =>
        (candidate.source === selection.source && candidate.target === selection.target) ||
        (candidate.source === selection.target && candidate.target === selection.source),
    )
    if (link) return <LinkDetail key={key} link={link} data={data} actions={actions} />
  }

  return (
    <ConnectionOverview
      key={key}
      result={result}
      sourceLabel={sourceLabel}
      targetLabel={targetLabel}
      data={data}
      actions={actions}
    />
  )
}

/** What the panel shows when nothing on the graph is selected: the answer
 * itself, stated once — connected or not, how strongly, and through whom. */
function ConnectionOverview({
  result,
  sourceLabel,
  targetLabel,
  data,
  actions,
}: {
  result: ConnectionResult
  sourceLabel: string
  targetLabel: string
  data: DetailData
  actions: DetailActions
}) {
  if (!result.connected) {
    return (
      <DetailShell
        kind="Connection"
        accent={ROOT_COLOR}
        title="No connection found"
        subtitle={
          <span className="text-secondary">
            {sourceLabel} → {targetLabel}
          </span>
        }
        tabs={[
          {
            id: 'overview',
            label: 'Overview',
            content: (
              <Section title="Result">
                <Callout>
                  Nothing links <strong>{sourceLabel}</strong> to <strong>{targetLabel}</strong>{' '}
                  within {result.max_degree_searched} degrees of separation.
                </Callout>
                <div style={{ marginTop: 'var(--space-3)' }}>
                  <FieldRow label="Degrees searched" value={result.max_degree_searched} />
                </div>
              </Section>
            ),
          },
        ]}
      />
    )
  }

  const { persons, links, confidence } = result.path
  const weakest = [...links].sort((a, b) => a.confidence - b.confidence)[0]

  const overview = (
    <>
      <Section title="How strong">
        <ConfidenceMeter value={confidence} label="Overall connection" />
        {weakest && confidenceTone(weakest.confidence) === 'weak' && (
          <Callout tone="warn">
            The chain is only as good as its weakest hop, and one of them is weak — treat this as a
            lead to check rather than a finding.
          </Callout>
        )}
      </Section>
      <Section title="Summary">
        <FieldRow label="From" value={sourceLabel} />
        <FieldRow label="To" value={targetLabel} />
        <FieldRow label="Hops" value={links.length} />
        <FieldRow label="People in the chain" value={persons.length} />
      </Section>
      <Section title="People" count={persons.length} hint="Click anyone to see their part in this.">
        {persons.map((person: PersonNode) => (
          <PersonRow
            key={person.id}
            person={person}
            fallbackId={person.id}
            onSelect={actions.openVid}
          />
        ))}
      </Section>
    </>
  )

  const hops = (
    <Section
      title="Every hop, in order"
      count={links.length}
      hint="Each one is a separate assertion — the overall score is the product of them all."
    >
      {links.map((link, i) => (
        <div className="connection-card" key={`${link.source}|${link.target}`}>
          <EntityRow
            label={`${persons[i]?.label ?? link.source} → ${persons[i + 1]?.label ?? link.target}`}
            meta={link.label}
            onSelect={() => actions.select({ kind: 'link', source: link.source, target: link.target })}
            right={
              <span className={`meter__value meter__value--${confidenceTone(link.confidence)}`}>
                {confidenceLabel(link.confidence)}
              </span>
            }
          />
          <div className="connection-card__reasons">
            {describeLink(link, data.attributesById, data.personsById).map((reason, j) => (
              <ReasonCard
                key={j}
                descriptor={reason}
                labelFor={actions.labelFor}
                onOpen={actions.openVid}
              />
            ))}
          </div>
        </div>
      ))}
    </Section>
  )

  const tabs: DetailTab[] = [
    { id: 'overview', label: 'Overview', content: overview },
    { id: 'hops', label: 'Hops', count: links.length, content: hops },
  ]

  return (
    <DetailShell
      kind="Connection"
      accent={ROOT_COLOR}
      title={`${sourceLabel} → ${targetLabel}`}
      subtitle={
        <span className="text-secondary">
          {links.length} hop{links.length === 1 ? '' : 's'} · {confidenceLabel(confidence)}
        </span>
      }
      tabs={tabs}
    />
  )
}
