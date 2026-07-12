import JsonView from './JsonView'

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  mutation: { isPending: boolean; isError: boolean; isSuccess: boolean; error: Error | null; data: unknown }
  title?: string
}

/** Standard spinner / error / JSON output block under each workbench form. */
export default function RunResult({ mutation, title }: Props) {
  return (
    <>
      {mutation.isPending && (
        <p className="row muted">
          <span className="spinner" /> Calling API…
        </p>
      )}
      {mutation.isError && <p className="error-text">{'\u2717'} {mutation.error?.message ?? 'Unknown error'}</p>}
      {mutation.isSuccess && (
        <JsonView data={mutation.data ?? { status: 'ok (empty response)' }} title={title} />
      )}
    </>
  )
}
