import InfoTooltip from './InfoTooltip'

interface Props {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
  info?: string
}

/** Labelled text input used by all workbench forms. */
export default function Field({ label, value, onChange, placeholder, type = 'text', info }: Props) {
  return (
    <label className="field">
      <span className="field__label">
        {label}
        {info && <InfoTooltip text={info} />}
      </span>
      <input
        className="input"
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}
