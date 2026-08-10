import type { PersonLink } from '../../../api/types'
import JsonView from '../../common/JsonView'
import { colorForDegree } from '../graphStyle'
import DetailShell, { type DetailTab } from './DetailShell'
import ReasonCard from './ReasonCard'
import { Callout, ConfidenceMeter, FieldRow, PersonRow, Section } from './parts'
import {
  confidenceLabel,
  confidenceTone,
  describeLink,
  type DetailActions,
  type DetailData,
} from './detailModel'

interface Props {
  link: PersonLink
  data: DetailData
  actions: DetailActions
}

/** What one arrow on the canvas actually asserts.
 *
 * A projected link is an *inference* — these two people share something —
 * so this view leads with how sure that inference is and then lists every
 * reason behind it separately, each traceable to the records that produced
 * it. The score is a noisy-OR across those reasons, which is why one strong
 * reason and three weak ones are worth telling apart. */
export default function LinkDetail({ link, data, actions }: Props) {
  const source = data.personsById.get(link.source)
  const target = data.personsById.get(link.target)
  const reasons = describeLink(link, data.attributesById, data.personsById)
  const tone = confidenceTone(link.confidence)

  const endpoints = (
    <Section title="Between">
      <PersonRow person={source} fallbackId={link.source} onSelect={actions.openVid} />
      <PersonRow person={target} fallbackId={link.target} onSelect={actions.openVid} />
    </Section>
  )

  const overview = (
    <>
      <Section title="How strong">
        <ConfidenceMeter value={link.confidence} label="Combined confidence" />
        {tone === 'weak' && (
          <Callout tone="warn">
            A weak link. {reasons.length === 1 ? 'It rests on a single reason' : 'Every reason behind it is thin'} —
            treat it as a lead to check, not a finding.
          </Callout>
        )}
      </Section>
      {endpoints}
      <Section title="Summary">
        <FieldRow label="Reasons" value={reasons.length} />
        <FieldRow label="Found at" value={`${link.degree} degree${link.degree === 1 ? '' : 's'} out`} />
        <FieldRow label="Kind" value={link.label} />
        <FieldRow
          label="Evidence types"
          value={[...new Set(reasons.map((reason) => reason.kind.replace(/_/g, ' ')))]}
        />
      </Section>
    </>
  )

  const reasonsTab = (
    <Section
      title="Why these two are connected"
      count={reasons.length}
      hint={
        reasons.length > 1
          ? 'Independent reasons compound: the combined score above is higher than any one of them.'
          : undefined
      }
    >
      {reasons.map((reason, i) => (
        <ReasonCard key={i} descriptor={reason} labelFor={actions.labelFor} onOpen={actions.openVid} />
      ))}
    </Section>
  )

  const raw = (
    <Section title="Projected link">
      <JsonView data={link} title="link" />
    </Section>
  )

  const tabs: DetailTab[] = [
    { id: 'overview', label: 'Overview', content: overview },
    { id: 'reasons', label: 'Reasons', count: reasons.length, content: reasonsTab },
    { id: 'raw', label: 'Raw', content: raw },
  ]

  return (
    <DetailShell
      kind="Relationship"
      accent={colorForDegree(link.degree) ?? '#64748b'}
      title={`${source?.label ?? link.source} ↔ ${target?.label ?? link.target}`}
      subtitle={<span className="text-secondary">{link.label}</span>}
      chips={
        <>
          <span className="tag-chip">{link.degree}° link</span>
          <span className={`tag-chip meter__value--${tone}`}>
            {confidenceLabel(link.confidence)} · {link.confidence.toFixed(2)}
          </span>
          <span className="tag-chip">
            {reasons.length} reason{reasons.length === 1 ? '' : 's'}
          </span>
        </>
      }
      actions={
        <button
          className="btn btn-sm"
          onClick={() => actions.tracePath(link.source, link.target)}
        >
          Trace path between them
        </button>
      }
      onClose={() => actions.select(null)}
      tabs={tabs}
    />
  )
}
