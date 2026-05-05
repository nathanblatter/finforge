import { useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { useGoal, useDeleteGoal, useUpdateGoalStatus } from '../../hooks/useGoals'
import { formatCurrency, formatDate, formatPct } from '../../utils/format'

const CURRENCY_GOAL_TYPES = new Set(['balance_target', 'portfolio_growth'])

function isCurrencyGoal(goalType: string): boolean {
  return CURRENCY_GOAL_TYPES.has(goalType)
}

function fmtVal(value: number | null, goalType: string): string {
  if (value === null) return '—'
  return isCurrencyGoal(goalType) ? formatCurrency(value) : value.toLocaleString()
}

function statusBadge(status: string): string {
  switch (status) {
    case 'On Track':  return 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
    case 'At Risk':   return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
    case 'Off Track': return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
    case 'Completed': return 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
    default:          return 'bg-slate-700 text-slate-500 border border-slate-600'
  }
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-900 rounded-lg p-3 flex flex-col gap-1 min-w-0">
      <span className="text-xs text-slate-500 uppercase tracking-wide truncate">{label}</span>
      <span className="text-sm font-semibold text-slate-100 truncate">{value}</span>
    </div>
  )
}

interface GoalDetailModalProps {
  goalId: string
  onClose: () => void
}

export default function GoalDetailModal({ goalId, onClose }: GoalDetailModalProps) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const { data: goal, isLoading, error } = useGoal(goalId)
  const deleteGoal = useDeleteGoal()
  const updateStatus = useUpdateGoalStatus()

  // Snapshots come newest-first from API; reverse for chart (oldest → newest)
  const chartData = goal?.snapshots
    ? [...goal.snapshots].reverse().map((s) => ({
        date: s.snapshot_date,
        pct: Number(s.pct_complete),
      }))
    : []

  const recentSnapshots = goal?.snapshots?.slice(0, 10) ?? []

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
          {isLoading || !goal ? (
            <div className="h-5 w-48 bg-slate-700 rounded animate-pulse" />
          ) : (
            <div className="flex items-center gap-3 min-w-0">
              <h2 className="text-base font-semibold text-slate-100 truncate">{goal.name}</h2>
              <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge(goal.progress_status)}`}>
                {goal.progress_status}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 ml-4 shrink-0">
            {goal && goal.status === 'active' && (
              <button
                onClick={() => updateStatus.mutate({ id: goalId, status: 'paused' }, { onSuccess: onClose })}
                className="text-xs text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 px-2.5 py-1 rounded-lg transition-colors"
              >
                Pause
              </button>
            )}
            {goal && goal.status === 'paused' && (
              <button
                onClick={() => updateStatus.mutate({ id: goalId, status: 'active' }, { onSuccess: onClose })}
                className="text-xs text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 px-2.5 py-1 rounded-lg transition-colors"
              >
                Resume
              </button>
            )}
            {goal && (
              <button
                onClick={() => {
                  if (confirm(`Delete "${goal.name}"? This cannot be undone.`)) {
                    deleteGoal.mutate(goalId, { onSuccess: onClose })
                  }
                }}
                className="text-xs text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 px-2.5 py-1 rounded-lg transition-colors"
              >
                Delete
              </button>
            )}
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-100 transition-colors text-xl leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 flex flex-col gap-6">
          {error && (
            <p className="text-sm text-rose-400 bg-rose-950/40 border border-rose-800/50 rounded-lg px-4 py-3">
              Failed to load goal details.
            </p>
          )}

          {isLoading && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-16 bg-slate-700 rounded-lg animate-pulse" />
                ))}
              </div>
              <div className="h-48 bg-slate-700 rounded-lg animate-pulse" />
            </div>
          )}

          {goal && (
            <>
              {/* Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricTile label="Current" value={fmtVal(goal.current_value, goal.goal_type)} />
                <MetricTile label="Target" value={fmtVal(goal.target_value, goal.goal_type)} />
                <MetricTile
                  label="Complete"
                  value={goal.pct_complete !== null ? formatPct(Number(goal.pct_complete)) : '—'}
                />
                <MetricTile
                  label="Proj. Completion"
                  value={goal.projected_completion_date ? formatDate(goal.projected_completion_date) : '—'}
                />
              </div>

              {/* Progress chart */}
              <div>
                <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                  Progress Over Time
                </h3>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: string) => {
                          const d = new Date(v + 'T00:00:00')
                          return `${d.toLocaleString('en-US', { month: 'short' })} ${d.getDate()}`
                        }}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: number) => `${v}%`}
                      />
                      <Tooltip
                        contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px', color: '#cbd5e1' }}
                        formatter={(value: number) => [`${value.toFixed(1)}%`, 'Complete']}
                        labelFormatter={(label: string) => formatDate(label)}
                      />
                      <Line
                        type="monotone"
                        dataKey="pct"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: '#38bdf8' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[200px] bg-slate-900 rounded-lg flex items-center justify-center">
                    <p className="text-slate-500 text-sm">Syncing data…</p>
                  </div>
                )}
              </div>

              {/* Snapshot table */}
              {recentSnapshots.length > 0 && (
                <div>
                  <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
                    Snapshot History
                  </h3>
                  <div className="overflow-x-auto rounded-lg border border-slate-700">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-700 bg-slate-900/60">
                          <th className="text-left text-xs text-slate-500 font-medium px-4 py-2.5">Date</th>
                          <th className="text-right text-xs text-slate-500 font-medium px-4 py-2.5">Value</th>
                          <th className="text-right text-xs text-slate-500 font-medium px-4 py-2.5">% Complete</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recentSnapshots.map((s, i) => (
                          <tr key={i} className="border-b border-slate-700/50 last:border-0 hover:bg-slate-700/30 transition-colors">
                            <td className="px-4 py-2.5 text-slate-300">{formatDate(s.snapshot_date)}</td>
                            <td className="px-4 py-2.5 text-right text-slate-300 tabular-nums">
                              {fmtVal(Number(s.current_value), goal.goal_type)}
                            </td>
                            <td className="px-4 py-2.5 text-right text-slate-400 tabular-nums">
                              {formatPct(Number(s.pct_complete))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
