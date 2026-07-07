import type { ImportReport } from '../../api/types'

export default function ImportReportView({ report }: { report: ImportReport }) {
  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>
        Imported <code>{report.filename}</code>
      </h3>
      <p className="muted" style={{ margin: 0 }}>
        Detected as {report.structure_kind === 'edge_list' ? 'a relationship list' : 'an entity table'}
        {report.tag && <> · node type <code>{report.tag}</code></>}
        {report.edge_type && <> · default relationship <code>{report.edge_type}</code></>}
      </p>
      <div className="row" style={{ flexWrap: 'wrap', gap: 'var(--space-5)' }}>
        <Stat label="Rows read" value={report.rows_read} />
        <Stat label="Nodes created" value={report.vertices_created} />
        <Stat label="Relationships created" value={report.edges_created} />
        <Stat label="Duplicates skipped" value={report.duplicates_skipped} />
        <Stat label="Elapsed" value={`${report.elapsed_seconds.toFixed(2)}s`} />
      </div>
      {report.validation_errors.length > 0 && (
        <details>
          <summary>{report.validation_errors.length} row(s) had issues</summary>
          <ul className="muted">
            {report.validation_errors.slice(0, 50).map((error, i) => (
              <li key={i}>{error}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div style={{ fontSize: '1.4em', fontWeight: 600 }}>{value}</div>
      <div className="muted">{label}</div>
    </div>
  )
}
