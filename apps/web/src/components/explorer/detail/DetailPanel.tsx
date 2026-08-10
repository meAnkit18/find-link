import type { GraphNode, PersonLink, PersonNetwork, RiskResult } from '../../../api/types'
import AttributeDetail from './AttributeDetail'
import CanvasOverview from './CanvasOverview'
import LinkDetail from './LinkDetail'
import PersonDetail from './PersonDetail'
import { selectionKey, type DetailActions, type DetailData, type Selection } from './detailModel'

interface Props {
  selection: Selection | null
  network: PersonNetwork | null
  canvasNodes: GraphNode[]
  data: DetailData
  actions: DetailActions
  risk: RiskResult | null
}

/** Picks the view for what's selected. One place decides "person or
 * attribute or link or nothing", so each view can assume its subject exists.
 *
 * Every view is keyed on the selection: switching subjects remounts it,
 * which is what resets the open tab instead of leaving the reader on a tab
 * that meant something on the previous entity. */
export default function DetailPanel({
  selection,
  network,
  canvasNodes,
  data,
  actions,
  risk,
}: Props) {
  const key = selectionKey(selection)

  if (selection?.kind === 'person') {
    const person = data.personsById.get(selection.id)
    if (person) {
      return (
        <PersonDetail
          key={key}
          person={person}
          data={data}
          actions={actions}
          risk={risk}
          isRoot={person.id === network?.root_id}
        />
      )
    }
  }

  if (selection?.kind === 'attribute') {
    const entry = data.attributesById.get(selection.id)
    if (entry) {
      return (
        <AttributeDetail
          key={key}
          attribute={entry.attribute}
          holders={entry.holders}
          data={data}
          actions={actions}
        />
      )
    }
  }

  if (selection?.kind === 'link') {
    const link = findLink(data.links, selection.source, selection.target)
    if (link) {
      return <LinkDetail key={key} link={link} data={data} actions={actions} />
    }
  }

  if (network) {
    return (
      <CanvasOverview
        key={key}
        network={network}
        canvasNodes={canvasNodes}
        data={data}
        actions={actions}
      />
    )
  }

  return (
    <div className="panel">
      <h3>Investigation tools</h3>
      <p className="text-secondary">
        Search for a person and pick a result. The canvas then shows the other people they're
        connected to — two people are connected when they share something (a phone, an email, an
        address, a passport, an employer) or have a direct relationship. "Degree" controls how far
        that chain runs: 1 is a direct share, 2 is a friend of a friend, 3 one step further.
      </p>
      <p className="text-secondary">
        Click any person to fan their own details out in a ring around them, and click again to fold
        them back in. Click a detail to see whose it is and what it matched, or click a link to see
        exactly what the two people have in common.
      </p>
    </div>
  )
}

/** The projection emits one link per pair, in whichever direction it found
 * it, so a selection made by clicking either end of the arrow has to match
 * both orientations. */
function findLink(links: PersonLink[], source: string, target: string): PersonLink | undefined {
  return links.find(
    (link) =>
      (link.source === source && link.target === target) ||
      (link.source === target && link.target === source),
  )
}
