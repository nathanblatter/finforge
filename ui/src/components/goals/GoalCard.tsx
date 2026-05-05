import type { GoalProgressResponse } from '../../types'
import { formatCurrency, formatDate } from '../../utils/format'

const CURRENCY_GOAL_TYPES = new Set(['balance_target', 'portfolio_growth'])

function isCurrencyGoal(goalType: string): boolean {
  return CURRENCY_GOAL_TYPES.has(goalType)
}

function statusColors(status: string) {
  switch (status) {
    case 'On Track':
      return { badge: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30', bar: 'bg-emerald-500' }
    case 'At Risk':
      return { badge: 'bg-amber-500/15 text-amber-400 border border-amber-500/30', bar: 'bg-amber-500' }
    case 'Off Track':
      return { badge: 'bg-rose-500/15 text-rose-400 border border-rose-500/30', bar: 'bg-rose-500' }
    case 'Completed':
      return { badge: 'bg-sky-500/15 text-sky-400 border border-sky-500/30', bar: 'bg-sky-500' }
    default:
      return { badge: 'bg-slate-700 text-slate-500 border border-slate-600', bar: 'bg-slate-600' }
  }
}

function formatValue(value: number | null, goalType: string): string {
  if (value === null) return '—'
  return isCurrencyGoal(goalType) ? formatCurrency(value) : value.toLocaleString()
}

interface GoalCardProps {
  goal: GoalProgressResponse
  onClick: () => void
}

export default function GoalCard({ goal, onClick }: GoalCardProps) {
  const colors = statusColors(goal.progress_status)
  const pct = goal.pct_complete !== null ? Math.min(Math.max(goal.pct_complete, 0), 100) : 0

  return (
    <div
      onClick={onClick}
      className="bg-slate-800 border border-slate-700 rounded-xl p-5 cursor-pointer transition-colors hover:border-slate-500 flex flex-col gap-3"
    >
      {/* Name + badge */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold text-slate-100 text-sm leading-snug">{goal.name}</h3>
        <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${colors.badge}`}>
          {goal.progress_status}
        </span>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${colors.bar}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>
            {formatValue(goal.current_value, goal.goal_type)}
            <span className="text-slate-600 mx-1">/</span>
            {formatValue(goal.target_value, goal.goal_type)}
          </span>
          <span className="tabular-nums">
            {goal.pct_complete !== null ? `${Number(goal.pct_complete).toFixed(1)}%` : '—'}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between gap-2 pt-0.5">
        <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full capitalize">
          {goal.cadence}
        </span>
        {goal.projected_completion_date && (
          <span className="text-slate-500 text-xs">
            Proj. {formatDate(goal.projected_completion_date)}
          </span>
        )}
      </div>
    </div>
  )
}
