import type { EntitySearchHit } from '../../../api/types'

interface Props {
  personA: EntitySearchHit | null
  personB: EntitySearchHit | null
  loading: boolean
}

/** What "Verify connection" shows before it has an answer: the query as a
 * schematic, in the same grammar the result is drawn in — two endpoint
 * cards with a span between them.
 *
 * The slots track the pickers in the topbar rather than restating a fixed
 * instruction, so the screen always shows which half of the question is
 * still missing. The span stays unresolved until a search returns, at which
 * point `ConnectionChainView` replaces this whole view with the real chain
 * on the canvas.
 *
 * It also spells out what counts as a link, because the result is unreadable
 * without that: a chain's hops are labelled in terms of these four kinds,
 * and nothing else in the mode defines them. */
export default function ConnectionBrief({ personA, personB, loading }: Props) {
  return (
    <div className="connection-brief">
      {/* `margin: auto 0` on this inner block is what centres the brief in
          the empty canvas without clipping its top once the viewport is
          shorter than the content — which `justify-content: center` on a
          scrolling column would do. */}
      <div className="connection-brief__inner">
        <div className="connection-brief__head">
          <h3 className="connection-brief__title">Are these two people connected?</h3>
          <p className="connection-brief__lede">
            The search walks outward from both people and returns the strongest chain it can
            find between them — or reports that there isn't one.
          </p>
        </div>

        <div className={`connection-schematic${loading ? ' connection-schematic--searching' : ''}`}>
          <EndpointNode label="Person A" hit={personA} />
          <div className="connection-span">
            <span className="connection-span__marker">?</span>
          </div>
          <EndpointNode label="Person B" hit={personB} />
        </div>

        {/* The one line that changes as the query fills in. Announced politely
            so the search starting and the slots filling reach a screen reader
            without stealing focus from the picker being used. */}
        <p className="connection-brief__status" role="status">
          {promptFor(personA, personB, loading)}
        </p>

        <dl className="connection-brief__kinds">
          <div>
            <dt>Direct relationship</dt>
            <dd>One is recorded as related to the other, with no one in between.</dd>
          </div>
          <div>
            <dt>Shared detail</dt>
            <dd>Both are attached to the same phone, address, or employer.</dd>
          </div>
          <div>
            <dt>Matching document value</dt>
            <dd>Separate documents state the same value — a father's name on two passports.</dd>
          </div>
          <div>
            <dt>Related employers</dt>
            <dd>They work at different organisations that are themselves connected.</dd>
          </div>
        </dl>
      </div>
    </div>
  )
}

/** Names the next thing to do, in the order the query has to be filled in.
 * "Find connection" is named exactly as the button is labelled — the same
 * action keeps the same name across the flow. */
function promptFor(
  personA: EntitySearchHit | null,
  personB: EntitySearchHit | null,
  loading: boolean,
): string {
  if (loading) return 'Searching for the strongest chain between them…'
  if (personA && personB) return 'Choose Find connection to search.'
  if (personA) return 'Pick Person B above to compare.'
  if (personB) return 'Pick Person A above to compare.'
  return 'Pick two people above to compare.'
}

/** One end of the query, drawn the way the canvas draws a person: a filled
 * dot with its name beneath it. Hollow and dashed until someone is picked,
 * so the schematic reads as the same kind of object the result is made of. */
function EndpointNode({ label, hit }: { label: string; hit: EntitySearchHit | null }) {
  return (
    <div className={`endpoint-node${hit ? ' endpoint-node--filled' : ''}`}>
      <span className="endpoint-node__dot" />
      <span className="endpoint-node__badge">{label}</span>
      <span className="endpoint-node__name">
        {hit ? hit.label || hit.entity_id : 'Not picked yet'}
      </span>
    </div>
  )
}
