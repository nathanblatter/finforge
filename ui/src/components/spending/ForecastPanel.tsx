import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { formatCurrency } from '../../utils/format'

export function useSpendingForecast() {
  return useQuery({
    queryKey: ['spending', 'forecast'],
    queryFn: api.getSpendingForecast,
    staleTime: 30 * 60 * 1000,
  })
}

export function useSpendingAnomalies() {
  return useQuery({
    queryKey: ['spending', 'anomalies'],
    queryFn: api.getSpendingAnomalies,
  })
}

export function useDismissAnomaly() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.dismissAnomaly(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['spending', 'anomalies'] }),
  })
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export function ForecastPanel() {
  const { data, isLoading } = useSpendingForecast()

  if (isLoading) return <Skeleton className="h-48" />
  if (!data || data.categories.length === 0) return null

  const monthLabel = new Date(`${data.forecast_month}-01T00:00:00`).toLocaleDateString('en-US', { month: 'long' })

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-slate-300">Next Month Forecast</h3>
        <span className="text-sm font-bold text-slate-100">{formatCurrency(data.total_forecast)}</span>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Expected {monthLabel} spend per category (exponential smoothing over your history, 80% band).
      </p>
      <div className="space-y-2.5">
        {data.categories.slice(0, 8).map((c) => {
          const pacingOver = c.mtd_projected > c.hi && c.mtd_spent > 0
          return (
            <div key={c.category}>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-300">{c.category}</span>
                <span className="text-slate-200 tabular-nums">{formatCurrency(c.forecast)}</span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>range {formatCurrency(c.lo)} – {formatCurrency(c.hi)}</span>
                {pacingOver && (
                  <span className="text-amber-400">pacing {formatCurrency(c.mtd_projected)} this month</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const REASON_LABELS: Record<string, string> = {
  outlier: 'Unusual amount',
  duplicate: 'Possible duplicate',
}

export function AnomaliesPanel() {
  const { data, isLoading } = useSpendingAnomalies()
  const dismiss = useDismissAnomaly()

  if (isLoading) return <Skeleton className="h-32" />
  const anomalies = data?.anomalies ?? []
  if (anomalies.length === 0) return null

  return (
    <div className="bg-slate-800 border border-amber-500/30 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-amber-400 mb-1">Unusual Activity</h3>
      <p className="text-xs text-slate-500 mb-4">
        Transactions that look statistically out of place — check for fraud or billing errors.
      </p>
      <div className="space-y-3">
        {anomalies.map((a) => (
          <div key={a.id} className="flex items-start justify-between gap-3 bg-slate-900/60 border border-slate-700 rounded-lg p-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-slate-100">{a.merchant_name ?? a.category ?? 'Unknown'}</span>
                <span className="text-sm text-rose-400 tabular-nums">{formatCurrency(a.amount)}</span>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400">
                  {REASON_LABELS[a.reason] ?? a.reason}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{a.detail}</p>
              <p className="text-[11px] text-slate-600 mt-0.5">{a.date} · {a.account_alias}</p>
            </div>
            <button
              onClick={() => dismiss.mutate(a.id)}
              disabled={dismiss.isPending}
              className="shrink-0 text-xs text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-50"
            >
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
