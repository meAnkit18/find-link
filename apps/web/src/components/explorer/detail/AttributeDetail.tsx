import { Zap } from 'lucide-react'
import type { EntityAttribute } from '../../../api/types'
import PropertiesList from '../../common/PropertiesList'
import { attributeNodeLabel, humanizeWords } from '../attributeLabel'
import { colorForTag } from '../graphStyle'
import DetailShell, { type DetailTab } from './DetailShell'
import ReasonCard from './ReasonCard'
import { Callout, CopyValue, EntityRow, FieldRow, PersonRow, Section } from './parts'
import {
  attributeFields,
  confidenceLabel,
  factProperties,
  confidenceTone,
  degreeText,
  describeLink,
  groupAttributesByTag,
  linksThroughConnector,
  otherEnd,
  type DetailActions,
  type DetailData,
} from './detailModel'

interface Props {
  attribute: EntityAttribute
  /** Everyone known to hold this attribute — the person whose expansion
   * pulled it in, plus whoever the projection says shares it. */
  holders: string[]
  data: DetailData
  actions: DetailActions
}

/** One attribute — a passport, an address, a phone — as its own subject.
 *
 * The heading is what the thing *is* ("Passport"), not its number, and the
 * panel then answers the two questions that follow from clicking it: whose
 * is it, and what did it connect. The holder's own record is inlined so
 * neither question costs a trip back through the person node. */
export default function AttributeDetail({ attribute, holders, data, actions }: Props) {
  const title = attributeNodeLabel(attribute)
  const kind = humanizeWords(attribute.tag)
  const fields = attributeFields(attribute, data.fieldMatches, holders)
  const identityFields = fields.filter((field) => field.group === 'identity')
  const claimFields = fields.filter((field) => field.group === 'claim')
  const matchedCount = claimFields.filter((field) => field.matchedWith.length > 0).length
  const explains = linksThroughConnector(data.links, attribute.id)
  const isShared = holders.length > 1

  function personLabel(id: string): string {
    return data.personsById.get(id)?.label ?? id
  }

  const heldBy = (
    <Section title="Held by" count={holders.length}>
      {holders.map((holderId) => (
        <PersonRow
          key={holderId}
          person={data.personsById.get(holderId)}
          fallbackId={holderId}
          onSelect={actions.openVid}
        />
      ))}
    </Section>
  )

  const overview = (
    <>
      {isShared && (
        <Callout tone="warn">
          The same {kind.toLowerCase()} appears on {holders.length} customer files. A shared
          document is the strongest claim this graph makes — treat it as a possible duplicate
          identity, not a coincidence.
        </Callout>
      )}
      {heldBy}
      <Section title={`${kind} details`}>
        {identityFields.length === 0 ? (
          <FieldRow label="Value" value={attribute.label} />
        ) : (
          identityFields.map((field) => (
            <FieldRow key={field.key} label={field.label} value={field.value} />
          ))
        )}
        <FieldRow label="Recorded via" value={attribute.edge_type || 'not recorded'} />
      </Section>
      <Section
        title="What it connected"
        count={explains.length}
        hint={
          explains.length === 0
            ? undefined
            : 'Links in the current projection that rest on this record.'
        }
      >
        {explains.length === 0 ? (
          <Callout>
            This {kind.toLowerCase()} connects nobody at the current confidence threshold — it's
            on record, but it isn't why anyone is on the canvas.
          </Callout>
        ) : (
          explains.slice(0, 3).map((link) => (
            <EntityRow
              key={`${link.source}|${link.target}`}
              label={`${personLabel(link.source)} ↔ ${personLabel(link.target)}`}
              meta={`${confidenceLabel(link.confidence)} · ${link.confidence.toFixed(2)}`}
              onSelect={() =>
                actions.select({ kind: 'link', source: link.source, target: link.target })
              }
            />
          ))
        )}
      </Section>
    </>
  )

  const fieldsTab = (
    <>
      <Section
        title="Recorded claims"
        count={claimFields.length}
        hint={
          matchedCount > 0
            ? 'Fields that produced a match are listed first and marked.'
            : 'None of these values matched anyone else in this projection.'
        }
      >
        {claimFields.length === 0 ? (
          <Callout>This record carries no claim fields beyond its own identity.</Callout>
        ) : (
          claimFields.map((field) => (
            <FieldRow
              key={field.key}
              label={field.label}
              value={field.value}
              flag={
                field.matchedWith.length > 0 ? (
                  <span className="match-flag">
                    <Zap size={11} />
                    also on{' '}
                    {field.matchedWith.map((id, i) => (
                      <span key={id}>
                        {i > 0 && ', '}
                        <button className="link-inline" onClick={() => actions.openVid(id)}>
                          {personLabel(id)}
                        </button>
                      </span>
                    ))}
                  </span>
                ) : undefined
              }
            />
          ))
        )}
      </Section>
      <Section title={`${kind} identity`} count={identityFields.length}>
        {identityFields.length === 0 ? (
          <FieldRow label="Value" value={attribute.label} />
        ) : (
          identityFields.map((field) => (
            <FieldRow key={field.key} label={field.label} value={field.value} />
          ))
        )}
      </Section>
    </>
  )

  const holderTab = (
    <>
      {holders.map((holderId) => {
        const holder = data.personsById.get(holderId)
        const otherAttributes = (data.attributes.get(holderId) ?? []).filter(
          (a) => a.id !== attribute.id,
        )
        const holderLinks = data.linksByPerson.get(holderId) ?? []
        return (
          <div key={holderId} className="holder-block">
            <Section title={holder?.label ?? holderId}>
              <FieldRow
                label="Distance"
                value={holder ? degreeText(holder.degree, data.rootLabel) : 'not on this canvas'}
              />
              {holder && <FieldRow label="Type" value={holder.entity_type} />}
              <FieldRow label="Connected people" value={holderLinks.length} />
              {holder && (
                <div style={{ marginTop: 'var(--space-2)' }}>
                  <PropertiesList
                    properties={factProperties(holder.properties)}
                    emptyLabel="No identity fields recorded."
                  />
                </div>
              )}
              <div className="holder-block__actions">
                <button className="btn btn-sm" onClick={() => actions.openVid(holderId)}>
                  Open full profile
                </button>
              </div>
            </Section>
            <Section title="Their other records" count={otherAttributes.length}>
              {otherAttributes.length === 0 ? (
                <Callout>
                  {data.loadingAttributes.has(holderId)
                    ? 'Loading their other records…'
                    : 'Nothing else on record for this person.'}
                </Callout>
              ) : (
                groupAttributesByTag(otherAttributes).map(([tag, list]) => (
                  <div key={tag} className="tag-group">
                    <span className="tag-chip">
                      <span className="tag-dot" style={{ background: colorForTag(tag) }} />
                      {tag.replace(/_/g, ' ')} ({list.length})
                    </span>
                    {list.map((other) => {
                      const otherTitle = attributeNodeLabel(other)
                      return (
                        <EntityRow
                          key={other.id}
                          label={otherTitle}
                          meta={otherTitle === other.label ? undefined : other.label}
                          accent={colorForTag(other.tag)}
                          onSelect={() => actions.select({ kind: 'attribute', id: other.id })}
                          right={
                            other.shared_with.length > 0 ? (
                              <span className="badge badge--warn">
                                shared ×{other.shared_with.length + 1}
                              </span>
                            ) : undefined
                          }
                        />
                      )
                    })}
                  </div>
                ))
              )}
            </Section>
          </div>
        )
      })}
    </>
  )

  const connectionsTab = (
    <Section title="Links this record explains" count={explains.length}>
      {explains.length === 0 ? (
        <Callout>Nothing in the current projection rests on this record.</Callout>
      ) : (
        explains.map((link) => {
          const primary = holders.includes(link.source) ? link.source : link.target
          const other = otherEnd(link, primary)
          const reasons = describeLink(link, data.attributesById, data.personsById)
          return (
            <div className="connection-card" key={`${link.source}|${link.target}`}>
              <PersonRow
                person={data.personsById.get(other)}
                fallbackId={other}
                meta={`with ${personLabel(primary)}`}
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
    </Section>
  )

  const raw = (
    <>
      <Section title="Identifier">
        <CopyValue value={attribute.id} />
      </Section>
      <Section title="All properties">
        <PropertiesList properties={attribute.properties} />
      </Section>
    </>
  )

  const tabs: DetailTab[] = [
    { id: 'overview', label: 'Overview', content: overview },
    { id: 'fields', label: 'Fields', count: fields.length, content: fieldsTab },
    {
      id: 'holder',
      label: holders.length > 1 ? 'Holders' : 'Holder',
      count: holders.length > 1 ? holders.length : undefined,
      content: holderTab,
    },
    { id: 'connections', label: 'Links', count: explains.length, content: connectionsTab },
    { id: 'raw', label: 'Raw', content: raw },
  ]

  return (
    <DetailShell
      kind={kind}
      accent={colorForTag(attribute.tag)}
      title={title}
      subtitle={<CopyValue value={title === attribute.label ? attribute.id : attribute.label} />}
      chips={
        <>
          <span className="tag-chip">
            <span className="tag-dot" style={{ background: colorForTag(attribute.tag) }} />
            {attribute.tag.replace(/_/g, ' ')}
          </span>
          <span className="tag-chip">
            {holders.length === 1
              ? `${personLabel(holders[0])}’s`
              : `held by ${holders.length} people`}
          </span>
          {matchedCount > 0 && (
            <span className="tag-chip tag-chip--active">
              {matchedCount} matching field{matchedCount === 1 ? '' : 's'}
            </span>
          )}
        </>
      }
      onClose={() => actions.select(null)}
      tabs={tabs}
    />
  )
}
