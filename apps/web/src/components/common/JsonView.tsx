import { useState } from 'react'

interface Props {
  data: unknown
  title?: string
  initiallyOpen?: boolean
}

/** Collapsible pretty-printed JSON block with copy-to-clipboard — the
 * workhorse of the manual-testing pages. */
export default function JsonView({ data, title = 'Response', initiallyOpen = true }: Props) {
  const [copied, setCopied] = useState(false)
  const text = JSON.stringify(data, null, 2)

  return (
    <details className="json-view" open={initiallyOpen}>
      <summary className="json-view__summary">
        <span>{title}</span>
        <button
          type="button"
          className="btn json-view__copy"
          onClick={(e) => {
            e.preventDefault()
            navigator.clipboard.writeText(text).then(() => {
              setCopied(true)
              setTimeout(() => setCopied(false), 1200)
            })
          }}
        >
          {copied ? 'Copied \u2713' : 'Copy'}
        </button>
      </summary>
      <pre className="json-view__pre">{text}</pre>
    </details>
  )
}
