import { useDownloadQueue, type DownloadJob } from '../../hooks/useDownloadQueue'

function SpinnerIcon() {
  return (
    <svg className="animate-spin h-4 w-4 text-sky-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className="text-emerald-400">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function ErrorIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className="text-rose-400">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function DismissButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="ml-2 p-0.5 rounded hover:bg-slate-600 text-slate-500 hover:text-slate-300 transition-colors"
      aria-label="Dismiss"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  )
}

function JobItem({ job, onDismiss }: { job: DownloadJob; onDismiss: () => void }) {
  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all duration-300 ${
        job.justCompleted
          ? 'bg-emerald-500/20 ring-1 ring-emerald-500/40'
          : 'bg-slate-700/50'
      }`}
    >
      {job.status === 'pending' && <SpinnerIcon />}
      {job.status === 'ready' && <CheckIcon />}
      {job.status === 'error' && <ErrorIcon />}

      {job.status === 'ready' && job.url ? (
        <a
          href={job.url}
          download={`${job.name}.pdf`}
          className="text-sky-400 hover:text-sky-300 underline underline-offset-2 truncate max-w-[200px]"
        >
          {job.name}
        </a>
      ) : (
        <span className={`truncate max-w-[200px] ${
          job.status === 'error' ? 'text-rose-300' : 'text-slate-300'
        }`}>
          {job.name}
        </span>
      )}

      {job.status === 'error' && job.error && (
        <span className="text-xs text-rose-400/70 truncate max-w-[150px]" title={job.error}>
          {job.error}
        </span>
      )}

      {job.status !== 'pending' && <DismissButton onClick={onDismiss} />}
    </div>
  )
}

export default function DownloadQueue() {
  const { jobs, dismissJob } = useDownloadQueue()

  if (jobs.length === 0) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-slate-800 border-t border-slate-700 px-4 py-2.5 shadow-lg">
      <div className="max-w-[1400px] mx-auto flex items-center gap-3 overflow-x-auto">
        <span className="text-xs font-medium text-slate-400 whitespace-nowrap flex-shrink-0">
          Downloads
        </span>
        {jobs.map(job => (
          <JobItem key={job.id} job={job} onDismiss={() => dismissJob(job.id)} />
        ))}
      </div>
    </div>
  )
}
