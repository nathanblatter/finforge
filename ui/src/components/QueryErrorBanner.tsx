interface Props {
  error: Error | null
  refetch?: () => void
}

export default function QueryErrorBanner({ error, refetch }: Props) {
  if (!error) return null

  return (
    <div className="rounded-md border border-rose-500/30 bg-rose-500/10 p-4 mb-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className="text-sm font-medium text-rose-400">Something went wrong</p>
          <p className="mt-1 text-sm text-slate-400">{error.message}</p>
        </div>
        {refetch && (
          <button
            onClick={refetch}
            className="shrink-0 rounded-md px-3 py-1.5 text-xs font-medium text-rose-400 border border-rose-500/30 hover:bg-rose-500/20 transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
