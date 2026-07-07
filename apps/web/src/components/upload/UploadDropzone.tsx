import { useRef, useState } from 'react'

interface Props {
  disabled?: boolean
  onFileSelected: (file: File) => void
}

export default function UploadDropzone({ disabled, onFileSelected }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  return (
    <div
      className="card"
      style={{
        borderStyle: 'dashed',
        borderColor: dragOver ? 'var(--color-primary)' : 'var(--color-border)',
        textAlign: 'center',
        padding: 'var(--space-6)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const file = e.dataTransfer.files[0]
        if (file && !disabled) onFileSelected(file)
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        style={{ display: 'none' }}
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFileSelected(file)
          e.target.value = ''
        }}
      />
      <p style={{ margin: 0, fontSize: '1.1em' }}>Drop a CSV here, or click to browse</p>
      <p className="muted" style={{ margin: 0 }}>
        A list of relationships (two entity columns) or a table of entities with an id column.
      </p>
    </div>
  )
}
