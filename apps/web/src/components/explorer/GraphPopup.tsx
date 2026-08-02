import { X } from 'lucide-react'

export type GraphPopupInfo =
  | { kind: 'node'; label: string; tag: string; color: string; role: 'main' | 'sub' }
  | { kind: 'edge'; label: string; source: string; target: string; color: string }

interface Props {
  info: GraphPopupInfo | null
  pinned: boolean
  onClose: () => void
}

/** Floating hover/pinned info card for the graph canvas, ported from
 * kindred-main's graph-popup.tsx. Deliberately a light card regardless of
 * the page theme, so it reads clearly against the dark canvas. */
export default function GraphPopup({ info, pinned, onClose }: Props) {
  if (!info) return null
  const isNode = info.kind === 'node'

  return (
    <div className={`graph-popup${pinned ? ' graph-popup--pinned' : ''}`}>
      <div className="graph-popup__header">
        <span className="graph-popup__dot" style={{ background: info.color }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="graph-popup__kind" style={{ color: info.color }}>
            {isNode ? info.tag : 'Relationship'}
          </div>
          <div className="graph-popup__title">
            {isNode ? (
              info.label
            ) : (
              <>
                {info.source} <span style={{ color: '#94a3b8' }}>→</span> {info.target}
              </>
            )}
          </div>
        </div>
        {pinned && (
          <button className="graph-popup__close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        )}
      </div>
      <div className="graph-popup__body">
        {isNode ? (
          <>
            <div className="graph-popup__row">
              <span className="graph-popup__row-key">Type</span>
              <span className="graph-popup__row-val">{info.tag}</span>
            </div>
            <div className="graph-popup__row">
              <span className="graph-popup__row-key">Role</span>
              <span className="graph-popup__row-val">{info.role === 'main' ? 'Hub node' : 'Attribute'}</span>
            </div>
          </>
        ) : (
          <>
            <div className="graph-popup__row">
              <span className="graph-popup__row-key">From</span>
              <span className="graph-popup__row-val">{info.source}</span>
            </div>
            <div className="graph-popup__row">
              <span className="graph-popup__row-key">To</span>
              <span className="graph-popup__row-val">{info.target}</span>
            </div>
            <div className="graph-popup__row">
              <span className="graph-popup__row-key">Type</span>
              <span className="graph-popup__row-val">{info.label}</span>
            </div>
          </>
        )}
        <p className="graph-popup__hint">{pinned ? 'Pinned — click the node/edge again, or ✕, to close' : 'Click to pin'}</p>
      </div>
    </div>
  )
}
