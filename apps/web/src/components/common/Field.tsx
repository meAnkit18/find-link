interface Props {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
}

/** Labelled text input used by all workbench forms. */
export default function Field({ label, value, onChange, placeholder, type = 'text' }: Props) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
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
