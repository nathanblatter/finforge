import { useState } from 'react'
import Header from '../components/layout/Header'
import AlertsList from '../components/goals/AlertsList'
import { useAlerts, useAcknowledgeAlert } from '../hooks/useAlerts'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-800 border border-slate-700 rounded-xl animate-pulse ${className}`} />
}

export default function AlertsPage() {
  const [includeAcknowledged, setIncludeAcknowledged] = useState(false)

  const { data, isLoading, error } = useAlerts(includeAcknowledged)
  const { mutate: acknowledge, isPending: isAcknowledging } = useAcknowledgeAlert()

  const alerts = data?.alerts ?? []
  const total = data?.total ?? 0
  const unacknowledgedCount = data?.unacknowledged_count ?? 0

  return (
    <div className="flex flex-col gap-6 max-w-[900px] mx-auto">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Alerts" />
        <button
          onClick={() => setIncludeAcknowledged((v) => !v)}
          className={[
            'text-sm font-medium px-3 py-1.5 rounded-lg border transition-colors',
            includeAcknowledged
              ? 'bg-slate-700 text-slate-100 border-slate-600'
              : 'text-slate-400 border-slate-700 hover:text-slate-200 hover:border-slate-500',
          ].join(' ')}
        >
          {includeAcknowledged ? 'Unacknowledged only' : 'Show all'}
        </button>
      </div>

      {!isLoading && !error && (
        <div className="flex items-center gap-6 text-sm">
          <span className="text-slate-400">
            <span className="font-semibold text-slate-200">{total}</span> total
          </span>
          {unacknowledgedCount > 0 ? (
            <span className="text-amber-400">
              <span className="font-semibold">{unacknowledgedCount}</span> unacknowledged
            </span>
          ) : (
            <span className="text-emerald-400 font-medium">All caught up</span>
          )}
        </div>
      )}

      {error && (
        <div className="bg-rose-950/40 border border-rose-800/50 rounded-xl p-4 text-sm text-rose-400">
          Failed to load alerts. Check API connection.
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-16" />)}
        </div>
      )}

      {!isLoading && !error && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl px-5 py-1">
          <AlertsList
            alerts={alerts}
            onAcknowledge={(id) => acknowledge(id)}
            isAcknowledging={isAcknowledging}
          />
        </div>
      )}
    </div>
  )
}
