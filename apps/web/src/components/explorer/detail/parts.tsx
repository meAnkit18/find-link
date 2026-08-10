// The small pieces the four detail views are assembled from. Presentational
// only: every decision they render (what a reason says, which fields
// matched, how a score reads) is made in detailModel.ts.

import { useState, type ReactNode } from 'react'
import { Check, Copy } from 'lucide-react'
import type { PersonNode } from '../../../api/types'
import { formatPropertyValue } from '../../common/format'
import { confidenceLabel, confidenceTone } from './detailModel'

/** A labelled block inside a tab. Sections are what make the panel scannable
 * — every group of facts says what it is and how many there are. */
export function Section({
  title,
  count,
  hint,
  children,
}: {
  title: string
  count?: number
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="detail-section">
      <div className="detail-section__head">
        <h4 className="detail-section__title">{title}</h4>
        {count !== undefined && <span className="badge">{count}</span>}
      </div>
      {hint && <p className="detail-section__hint">{hint}</p>}
      {children}
    </section>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="detail-empty">{children}</p>
}

/** A callout for something the panel wants to say outright rather than leave
 * the reader to infer — a document held by two people, a link that rests on
 * one weak reason. */
export function Callout({ tone = 'info', children }: { tone?: 'info' | 'warn'; children: ReactNode }) {
  return <div className={`detail-callout detail-callout--${tone}`}>{children}</div>
}

/** One label/value line. `flag` carries the annotation that makes the panel
 * useful — "also on Yusuf Rahman's records". */
export function FieldRow({
  label,
  value,
  flag,
}: {
  label: string
  value: unknown
  flag?: ReactNode
}) {
  const formatted = formatPropertyValue(value)
  return (
    <div className={`field-row${flag ? ' field-row--flagged' : ''}`}>
      <div className="field-row__key">{label}</div>
      <div className="field-row__value">
        {formatted.kind === 'empty' ? (
          <span className="muted">Not recorded</span>
        ) : formatted.kind === 'list' ? (
          <div className="row" style={{ flexWrap: 'wrap', gap: 4 }}>
            {formatted.items.map((item, i) => (
              <span key={i} className="badge">
                {item}
              </span>
            ))}
          </div>
        ) : formatted.kind === 'code' ? (
          <span className="mono">{formatted.text}</span>
        ) : (
          formatted.text
        )}
        {flag && <div className="field-row__flag">{flag}</div>}
      </div>
    </div>
  )
}

/** An identifier with a copy button. Passport numbers and entity ids exist to
 * be pasted into another system, and selecting text inside a graph panel is
 * fiddly. */
export function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    // Absent outside a secure context. Confirming a copy that never happened
    // would be worse than doing nothing — the value is still on screen to
    // select by hand, so this needs no error state either.
    if (!navigator.clipboard) return
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1200)
    } catch {
      // Permission denied. Same reasoning: stay quiet.
    }
  }

  return (
    <span className="copy-value">
      <span className="mono">{value}</span>
      <button
        className="copy-value__btn"
        onClick={copy}
        aria-label={copied ? 'Copied' : `Copy ${value}`}
        title="Copy"
      >
        {copied ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </span>
  )
}

/** A link's score, as a bar plus the band it falls in. */
export function ConfidenceMeter({ value, label = 'Confidence' }: { value: number; label?: string }) {
  const tone = confidenceTone(value)
  return (
    <div className="meter">
      <div className="meter__head">
        <span className="meter__label">{label}</span>
        <span className={`meter__value meter__value--${tone}`}>
          {confidenceLabel(value)} · {value.toFixed(2)}
        </span>
      </div>
      <div className="meter__track">
        <div
          className={`meter__fill meter__fill--${tone}`}
          style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
        />
      </div>
    </div>
  )
}

export function DegreeBadge({ degree }: { degree: number }) {
  return <span className="badge">{degree === 0 ? 'searched' : `${degree}°`}</span>
}

/** A clickable person row — the panel's main means of navigation. */
export function PersonRow({
  person,
  fallbackId,
  meta,
  right,
  onSelect,
}: {
  person: PersonNode | undefined
  fallbackId: string
  meta?: ReactNode
  right?: ReactNode
  onSelect: (id: string) => void
}) {
  const id = person?.id ?? fallbackId
  return (
    <button className="entity-row" onClick={() => onSelect(id)}>
      <div className="entity-row__main">
        <span className="entity-row__name">{person?.label ?? fallbackId}</span>
        {meta && <span className="entity-row__meta">{meta}</span>}
      </div>
      <span className="entity-row__right">
        {right}
        {person && <DegreeBadge degree={person.degree} />}
      </span>
    </button>
  )
}

/** A clickable non-person row (a document, a phone, an organisation). */
export function EntityRow({
  label,
  meta,
  accent,
  right,
  onSelect,
  disabled,
}: {
  label: string
  meta?: ReactNode
  accent?: string
  right?: ReactNode
  onSelect?: () => void
  disabled?: boolean
}) {
  return (
    <button className="entity-row" onClick={onSelect} disabled={disabled || !onSelect}>
      <div className="entity-row__main">
        <span className="entity-row__name">
          {accent && <span className="tag-dot" style={{ background: accent, marginRight: 6 }} />}
          {label}
        </span>
        {meta && <span className="entity-row__meta">{meta}</span>}
      </div>
      {right && <span className="entity-row__right">{right}</span>}
    </button>
  )
}
