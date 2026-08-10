import { useState, type ReactNode } from 'react'

export interface DetailTab {
  id: string
  label: string
  /** Shown as a pill on the tab, so "how much is in there" reads without
   * opening it. Omit for a tab whose content isn't a list. */
  count?: number
  content: ReactNode
}

interface Props {
  /** The eyebrow above the title: what *kind* of thing this is
   * ("Passport", "Person", "Relationship"). */
  kind: string
  /** Tag/degree color for the header dot, tying the panel to the node the
   * user clicked on the canvas. */
  accent: string
  title: string
  /** The identifying value under the title — a passport number, an entity
   * id. Usually wrapped in <CopyValue>. */
  subtitle?: ReactNode
  chips?: ReactNode
  /** Buttons that act on this entity. Rendered in the fixed header rather
   * than in a tab, so they stay reachable whichever tab is open. */
  actions?: ReactNode
  tabs: DetailTab[]
  onClose?: () => void
}

/** The frame every detail view shares: a typed header that stays put while
 * the body scrolls, over a tab strip.
 *
 * Mount it with a `key` tied to the selection (see `selectionKey`) — that's
 * what resets to the first tab when the user clicks a different entity,
 * instead of landing on whichever tab happened to be open on the last one.
 */
export default function DetailShell({
  kind,
  accent,
  title,
  subtitle,
  chips,
  actions,
  tabs,
  onClose,
}: Props) {
  const [activeId, setActiveId] = useState<string | null>(null)
  // Tabs are rebuilt every render and some are conditional (a person with no
  // risk result yet has no Risk tab), so the active id has to be resolved
  // against the current list rather than trusted.
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0]

  return (
    <div className="detail-panel">
      <header className="detail-panel__header">
        <div className="detail-panel__kind">
          <span className="tag-dot" style={{ background: accent }} />
          <span>{kind}</span>
        </div>
        {onClose && (
          <button className="detail-panel__close" onClick={onClose} aria-label="Clear selection">
            ✕
          </button>
        )}
        <h3 className="detail-panel__title">{title}</h3>
        {subtitle && <div className="detail-panel__subtitle">{subtitle}</div>}
        {chips && <div className="detail-panel__chips">{chips}</div>}
        {actions && <div className="detail-panel__actions">{actions}</div>}
        <div className="detail-tabs" role="tablist" aria-label={`${kind} sections`}>
          {tabs.map((tab) => {
            const isActive = tab.id === active?.id
            return (
              <button
                key={tab.id}
                role="tab"
                id={`detail-tab-${tab.id}`}
                aria-selected={isActive}
                aria-controls={`detail-tabpanel-${tab.id}`}
                className={`detail-tab${isActive ? ' detail-tab--active' : ''}`}
                onClick={() => setActiveId(tab.id)}
              >
                {tab.label}
                {tab.count !== undefined && <span className="detail-tab__count">{tab.count}</span>}
              </button>
            )
          })}
        </div>
      </header>

      {active && (
        <div
          className="detail-panel__body"
          role="tabpanel"
          id={`detail-tabpanel-${active.id}`}
          aria-labelledby={`detail-tab-${active.id}`}
          tabIndex={0}
        >
          {active.content}
        </div>
      )}
    </div>
  )
}
