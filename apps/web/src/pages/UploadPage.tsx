import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import UploadDropzone from '../components/upload/UploadDropzone'
import ImportReportView from '../components/upload/ImportReportView'

export default function UploadPage() {
  const { graphId } = useParams<{ graphId: string }>()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [jobId, setJobId] = useState<string | null>(null)

  const startImport = useMutation({
    mutationFn: (file: File) => api.startImport(graphId!, file),
    onSuccess: (job) => setJobId(job.job_id),
  })

  const jobQuery = useQuery({
    queryKey: ['import-job', graphId, jobId],
    queryFn: () => api.getImportJob(graphId!, jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data && ['done', 'failed'].includes(query.state.data.status) ? false : 500,
  })

  const job = jobQuery.data
  const isRunning = startImport.isPending || (job && ['pending', 'running'].includes(job.status))

  useEffect(() => {
    if (job?.status === 'done') {
      queryClient.invalidateQueries({ queryKey: ['graphs'] })
      queryClient.invalidateQueries({ queryKey: ['schema', graphId] })
    }
  }, [job?.status, graphId, queryClient])

  return (
    <main className="page">
      <div className="container stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Import a CSV</h2>
          <Link to="/">← All graphs</Link>
        </div>

        {!job && (
          <UploadDropzone
            disabled={startImport.isPending}
            onFileSelected={(file) => startImport.mutate(file)}
          />
        )}

        {isRunning && (
          <div className="card row">
            <span className="spinner" />
            <span>Reading and importing your file…</span>
          </div>
        )}

        {startImport.isError && (
          <p style={{ color: 'var(--color-danger)' }}>{(startImport.error as Error).message}</p>
        )}

        {job?.status === 'failed' && (
          <p style={{ color: 'var(--color-danger)' }}>Import failed: {job.error}</p>
        )}

        {job?.status === 'done' && job.report && (
          <div className="stack">
            <ImportReportView report={job.report} />
            <div className="row">
              <button className="btn btn--primary" onClick={() => navigate(`/graphs/${graphId}`)}>
                Explore this graph
              </button>
              <button className="btn" onClick={() => setJobId(null)}>
                Import another file
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
