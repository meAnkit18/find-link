interface Props {
  text: string
  className?: string
}

/** Small ⓘ icon that reveals a short plain-English explanation on hover
 * (or keyboard focus). Used beside buttons, inputs, and any field whose
 * meaning isn't obvious to a non-technical user. */
export default function InfoTooltip({ text, className }: Props) {
  return (
    <span className={`info-tooltip${className ? ` ${className}` : ''}`} tabIndex={0}>
      <span className="info-tooltip__icon" aria-hidden="true">i</span>
      <span className="info-tooltip__popover" role="tooltip">{text}</span>
      <span className="sr-only">{text}</span>
    </span>
  )
}
