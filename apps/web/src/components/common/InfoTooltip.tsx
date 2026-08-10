import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  text: string
  className?: string
}

// Keeps the popover clear of the viewport edge and lets it clear the arrow
// without the arrow running into the popover's rounded corners.
const VIEWPORT_MARGIN = 8
const ANCHOR_GAP = 8
const ARROW_INSET = 12

interface PopoverStyle {
  top: number
  left: number
  arrowLeft: number
  placement: 'top' | 'bottom'
}

/** Small ⓘ icon that reveals a short plain-English explanation on hover
 * (or keyboard focus). Used beside buttons, inputs, and any field whose
 * meaning isn't obvious to a non-technical user.
 *
 * The popover renders through a portal into `document.body` and is placed
 * with `position: fixed`, computed from the icon's own rect. Every panel in
 * this app clips overflow (rounded corners, scrolling lists), so a popover
 * positioned relative to the icon — the original approach — got clipped
 * whenever the icon sat near a panel edge. Escaping to `body` sidesteps
 * every one of those ancestors at once instead of special-casing each. */
export default function InfoTooltip({ text, className }: Props) {
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLSpanElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const [style, setStyle] = useState<PopoverStyle>({ top: 0, left: 0, arrowLeft: 0, placement: 'top' })

  useLayoutEffect(() => {
    if (!open) return
    const anchor = anchorRef.current
    const popover = popoverRef.current
    if (!anchor || !popover) return

    const anchorRect = anchor.getBoundingClientRect()
    const popoverRect = popover.getBoundingClientRect()

    const placement: PopoverStyle['placement'] =
      anchorRect.top - ANCHOR_GAP - popoverRect.height < VIEWPORT_MARGIN ? 'bottom' : 'top'
    const top = placement === 'top' ? anchorRect.top - ANCHOR_GAP - popoverRect.height : anchorRect.bottom + ANCHOR_GAP

    const idealLeft = anchorRect.left + anchorRect.width / 2 - popoverRect.width / 2
    const maxLeft = Math.max(window.innerWidth - popoverRect.width - VIEWPORT_MARGIN, VIEWPORT_MARGIN)
    const left = Math.min(Math.max(idealLeft, VIEWPORT_MARGIN), maxLeft)

    const idealArrowLeft = anchorRect.left + anchorRect.width / 2 - left
    const arrowLeft = Math.min(Math.max(idealArrowLeft, ARROW_INSET), popoverRect.width - ARROW_INSET)

    setStyle({ top, left, arrowLeft, placement })
  }, [open, text])

  return (
    <span
      ref={anchorRef}
      className={`info-tooltip${className ? ` ${className}` : ''}`}
      tabIndex={0}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span className="info-tooltip__icon" aria-hidden="true">i</span>
      {createPortal(
        <div
          ref={popoverRef}
          role="tooltip"
          className={`info-tooltip__popover info-tooltip__popover--${style.placement}${open ? ' info-tooltip__popover--open' : ''}`}
          style={{ top: style.top, left: style.left }}
        >
          {text}
          <span className="info-tooltip__arrow" style={{ left: style.arrowLeft }} />
        </div>,
        document.body,
      )}
      <span className="sr-only">{text}</span>
    </span>
  )
}
