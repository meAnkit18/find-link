import { colorForTag } from '../graphStyle'
import { ConfidenceMeter } from './parts'
import type { ReasonDescriptor } from './detailModel'

interface Props {
  descriptor: ReasonDescriptor
  /** A vid's display label, or null when the graph on screen doesn't know it
   * — a document that only exists on the far side of a match, whose person
   * has never been expanded. Those render as plain ids rather than as dead
   * buttons that would select a node the canvas doesn't have. */
  labelFor: (vid: string) => string | null
  onOpen: (vid: string) => void
}

/** One reason two people are linked, stated in full: what kind of evidence it
 * is, what it actually says, and which nodes it rests on.
 *
 * This is the audit trail — a reason an investigator can't trace back to a
 * document is a reason they can't put in a report. */
export default function ReasonCard({ descriptor, labelFor, onOpen }: Props) {
  const { heading, detail, connector, linked, fields, confidence, documentIds } = descriptor

  return (
    <div className="reason-card">
      <div className="reason-card__head">
        <span className="reason-card__kind">{heading}</span>
        {fields && fields.length > 1 && <span className="badge">cross-field</span>}
      </div>
      <p className="reason-card__detail">{detail}</p>

      {(connector || linked) && (
        <div className="reason-card__nodes">
          {[connector, linked]
            .filter((node): node is NonNullable<typeof node> => node != null)
            .map((node) => (
              <button
                key={node.id}
                className="node-chip"
                onClick={() => onOpen(node.id)}
                title={`Open ${node.label}`}
              >
                <span className="tag-dot" style={{ background: colorForTag(node.tag) }} />
                {node.label}
              </button>
            ))}
        </div>
      )}

      {documentIds && documentIds.length > 0 && (
        <div className="reason-card__sources">
          <span className="reason-card__sources-label">Stated in</span>
          {documentIds.map((id) => {
            const label = labelFor(id)
            return label ? (
              <button key={id} className="node-chip" onClick={() => onOpen(id)} title={`Open ${label}`}>
                <span className="tag-dot" style={{ background: colorForTag('document') }} />
                {label}
              </button>
            ) : (
              <span key={id} className="node-chip node-chip--static mono">
                {id}
              </span>
            )
          })}
        </div>
      )}

      {confidence !== undefined && (
        <ConfidenceMeter value={confidence} label="This reason alone" />
      )}
    </div>
  )
}
