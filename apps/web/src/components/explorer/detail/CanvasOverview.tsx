import type { GraphNode, PersonNetwork } from '../../../api/types'
import { humanizeLabel } from '../../common/format'
import { colorForTag } from '../graphStyle'
import DetailShell, { type DetailTab } from './DetailShell'
import { Callout, ConfidenceMeter, EntityRow, FieldRow, PersonRow, Section } from './parts'
import { confidenceLabel, type DetailActions, type DetailData } from './detailModel'

interface Props {
  network: PersonNetwork
  /** Everything currently drawn, so the attribute half of the list reflects
   * the canvas rather than the whole cache. */
  canvasNodes: GraphNode[]
  data: DetailData
  actions: DetailActions
}

/** What the panel shows when nothing is selected: the canvas itself,
 * described. Keeps a single place to see everything at once instead of
 * having to click every node to find out what's on screen. */
export default function CanvasOverview({ network, canvasNodes, data, actions }: Props) {
  const people = [...data.personsById.values()].sort(
    (a, b) => a.degree - b.degree || a.label.localeCompare(b.label),
  )
  const strongest = [...data.links].sort((a, b) => b.confidence - a.confidence).slice(0, 3)

  const attributesByTag = new Map<string, GraphNode[]>()
  for (const node of canvasNodes) {
    if (data.personsById.has(node.vid)) continue // people are listed on their own tab
    const tag = node.tags[0] ?? 'attribute'
    const list = attributesByTag.get(tag)
    if (list) list.push(node)
    else attributesByTag.set(tag, [node])
  }
  const attributeGroups = [...attributesByTag.entries()].sort((a, b) => b[1].length - a[1].length)
  const attributeCount = attributeGroups.reduce((total, [, list]) => total + list.length, 0)

  const overview = (
    <>
      <Section title="This projection">
        <FieldRow label="Searched person" value={data.rootLabel} />
        <FieldRow label="People shown" value={people.length} />
        <FieldRow label="Links found" value={data.links.length} />
        <FieldRow label="Degree" value={`${network.degree} out`} />
        <FieldRow label="Min confidence" value={network.min_confidence.toFixed(2)} />
        <FieldRow label="Details fanned out" value={attributeCount} />
      </Section>
      <Section
        title="Strongest links"
        count={strongest.length}
        hint="Where to look first — the connections this projection is most sure of."
      >
        {strongest.length === 0 ? (
          <Callout>No links at the current degree and confidence.</Callout>
        ) : (
          strongest.map((link) => (
            <div className="connection-card" key={`${link.source}|${link.target}`}>
              <EntityRow
                label={`${data.personsById.get(link.source)?.label ?? link.source} ↔ ${
                  data.personsById.get(link.target)?.label ?? link.target
                }`}
                meta={confidenceLabel(link.confidence)}
                onSelect={() =>
                  actions.select({ kind: 'link', source: link.source, target: link.target })
                }
              />
              <ConfidenceMeter value={link.confidence} />
            </div>
          ))
        )}
      </Section>
    </>
  )

  const peopleTab = (
    <Section title="Everyone on this canvas" count={people.length}>
      {people.map((person) => (
        <PersonRow
          key={person.id}
          person={person}
          fallbackId={person.id}
          meta={person.entity_type}
          onSelect={actions.openVid}
        />
      ))}
    </Section>
  )

  const detailsTab = (
    <>
      {attributeGroups.length === 0 ? (
        <Callout>
          No details fanned out yet. Click a person on the canvas to open their documents and
          contact records.
        </Callout>
      ) : (
        attributeGroups.map(([tag, nodes]) => (
          <Section key={tag} title={humanizeLabel(tag)} count={nodes.length}>
            {nodes.map((node) => (
              <EntityRow
                key={node.vid}
                label={node.label}
                accent={colorForTag(tag)}
                onSelect={() => actions.select({ kind: 'attribute', id: node.vid })}
              />
            ))}
          </Section>
        ))
      )}
    </>
  )

  const tabs: DetailTab[] = [
    { id: 'overview', label: 'Overview', content: overview },
    { id: 'people', label: 'People', count: people.length, content: peopleTab },
    { id: 'details', label: 'Details', count: attributeCount, content: detailsTab },
  ]

  return (
    <DetailShell
      kind="Canvas"
      accent={colorForTag('person')}
      title={`Network around ${data.rootLabel}`}
      subtitle={
        <span className="text-secondary">
          Nothing selected — click a person, a detail, or a link to inspect it.
        </span>
      }
      tabs={tabs}
    />
  )
}
