import type { ConnectionResult, PersonNode } from '../../../api/types'
import { describeLink } from '../detail/detailModel'
import ReasonCard from '../detail/ReasonCard'
import { Callout, ConfidenceMeter } from '../detail/parts'

interface Props {
  sourceLabel: string
  targetLabel: string
  result: ConnectionResult
  onExplore: (personId: string) => void
}

// The chain view has no canvas/detail-panel selection framework behind it,
// so a reason's connector/document chips render as inert labels here —
// the same fallback ReasonCard already uses for a node the screen doesn't
// know about (see its `labelFor` contract).
const noLabel = () => null
const noOpen = () => {}

/** The answer to "are these two people connected, and why" — a plain,
 * standalone chain, independent of the canvas. Reuses `describeLink` and
 * `ReasonCard` unchanged, so each hop reads exactly like an entry in the
 * Connections tab. */
export default function ConnectionChainView({ sourceLabel, targetLabel, result, onExplore }: Props) {
  if (!result.connected) {
    return (
      <div className="connection-chain">
        <Callout>
          No connection found between <strong>{sourceLabel}</strong> and{' '}
          <strong>{targetLabel}</strong> within {result.max_degree_searched} degrees of
          separation.
        </Callout>
      </div>
    )
  }

  const { persons, links, confidence } = result.path
  const personsById = new Map(persons.map((p) => [p.id, p]))

  return (
    <div className="connection-chain">
      <div className="connection-chain__summary">
        <h3>
          {sourceLabel} → {targetLabel}
        </h3>
        <ConfidenceMeter value={confidence} label="Overall connection" />
      </div>

      {persons.map((person, i) => (
        <div className="connection-chain__hop" key={person.id}>
          <PersonRow person={person} isEndpoint={i === 0 || i === persons.length - 1} onExplore={onExplore} />
          {links[i] && (
            <div className="connection-chain__reasons">
              {describeLink(links[i], new Map(), personsById).map((descriptor, j) => (
                <ReasonCard key={j} descriptor={descriptor} labelFor={noLabel} onOpen={noOpen} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function PersonRow({
  person,
  isEndpoint,
  onExplore,
}: {
  person: PersonNode
  isEndpoint: boolean
  onExplore: (personId: string) => void
}) {
  return (
    <div className="connection-chain__person">
      <div>
        <strong>{person.label}</strong>
        {!isEndpoint && (
          <span className="badge" style={{ marginLeft: 8 }}>
            via
          </span>
        )}
      </div>
      <button className="btn btn-sm" onClick={() => onExplore(person.id)}>
        Explore this person
      </button>
    </div>
  )
}
