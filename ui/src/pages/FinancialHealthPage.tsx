import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import Header from '../components/layout/Header'
import { useFinancialHealth, useFinancialHealthHistory } from '../hooks/useFinancialHealth'
import type { FinancialHealthComponent } from '../types'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function scoreBand(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Excellent', color: 'text-emerald-400' }
  if (score >= 60) return { label: 'Good', color: 'text-sky-400' }
  if (score >= 40) return { label: 'Fair', color: 'text-amber-400' }
  return { label: 'Needs attention', color: 'text-rose-400' }
}

function formatValue(component: FinancialHealthComponent): string {
  if (component.value === null || component.value === undefined) return '—'
  if (component.unit === '%') return `${component.value.toFixed(1)}%`
  if (component.unit === 'months') return `${component.value.toFixed(1)} mo`
  if (component.unit === 'CV') return component.value.toFixed(2)
  return `${component.value}`
}

const COMPONENT_ORDER: Array<keyof FinancialHealthResponseComponents> = [
  'savings_rate',
  'emergency_fund',
  'expense_volatility',
  'allocation_drift',
]

type FinancialHealthResponseComponents = {
  savings_rate: FinancialHealthComponent
  emergency_fund: FinancialHealthComponent
  expense_volatility: FinancialHealthComponent
  allocation_drift: FinancialHealthComponent
}

function ComponentCard({ id, component, expanded, onToggle }: {
  id: string
  component: FinancialHealthComponent
  expanded: boolean
  onToggle: () => void
}) {
  const band = scoreBand(component.score)
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <button onClick={onToggle} className="w-full flex items-center justify-between text-left">
        <div>
          <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{component.label}</div>
          <div className="flex items-baseline gap-2">
            <span className={`text-2xl font-bold ${band.color}`}>{component.score.toFixed(0)}</span>
            <span className="text-xs text-slate-500">/ 100</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm text-slate-300 tabular-nums">{formatValue(component)}</div>
          <div className="text-[11px] text-slate-600">weight {(component.weight * 100).toFixed(0)}%</div>
        </div>
      </button>
      {expanded && (
        <p className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-700 leading-relaxed">
          {component.detail}
        </p>
      )}
    </div>
  )
}

export default function FinancialHealthPage() {
  const { data, isLoading, error } = useFinancialHealth()
  const { data: history, isLoading: historyLoading } = useFinancialHealthHistory(24)
  const [expanded, setExpanded] = useState<string | null>(null)

  const chartData = (history?.snapshots ?? []).map((s) => ({
    date: s.snapshot_date.slice(0, 7),
    score: s.composite_score,
  }))

  const band = data ? scoreBand(data.composite_score) : null
  const topLeverComponent = data && data.top_lever
    ? data.components[data.top_lever as keyof FinancialHealthResponseComponents]
    : null

  return (
    <div className="space-y-6 max-w-[900px]">
      <Header title="Financial Health Score" />
      <p className="text-sm text-slate-500 -mt-2">
        A composite 0–100 score blended from savings rate, emergency-fund runway, expense volatility,
        and allocation drift — recomputed live, snapshotted monthly for the trend below.
      </p>

      <div className="bg-gradient-to-br from-slate-800 to-slate-800/60 border border-sky-500/20 rounded-xl p-6">
        {isLoading ? (
          <Skeleton className="h-32" />
        ) : error || !data ? (
          <p className="text-sm text-slate-500 py-8 text-center">Not enough data yet to compute a score.</p>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center gap-6">
            <div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">
                🩺 Financial Health — as of {data.as_of}
              </div>
              <div className="flex items-baseline gap-3">
                <span className={`text-6xl font-extrabold ${band?.color}`}>{data.composite_score.toFixed(0)}</span>
                <span className="text-lg text-slate-500">/ 100</span>
              </div>
              <div className={`text-sm font-semibold mt-1 ${band?.color}`}>{band?.label}</div>
            </div>
            {topLeverComponent && (
              <div className="sm:ml-auto bg-slate-900/60 border border-slate-700 rounded-lg p-4 max-w-sm">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">Biggest lever</div>
                <div className="text-sm text-slate-200 font-medium">{topLeverComponent.label}</div>
                <p className="text-xs text-slate-400 mt-1">
                  Maxing this component out would add up to{' '}
                  <span className="text-sky-400 font-semibold">
                    +{data.sensitivity[0]?.potential_gain.toFixed(1)}
                  </span>{' '}
                  composite points — the single biggest move available right now.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Trend</h3>
        {historyLoading ? (
          <Skeleton className="h-[200px]" />
        ) : chartData.length < 2 ? (
          <div className="h-[200px] bg-slate-900 rounded-lg flex items-center justify-center">
            <p className="text-xs text-slate-500">Not enough monthly snapshots yet — check back after the next monthly run.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={{ stroke: '#334155' }} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 11 }} axisLine={{ stroke: '#334155' }} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px', color: '#cbd5e1' }}
                formatter={(value: number) => [value.toFixed(1), 'Score']}
              />
              <Line type="monotone" dataKey="score" stroke="#38bdf8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {data && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Breakdown</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {COMPONENT_ORDER.map((key) => (
              <ComponentCard
                key={key}
                id={key}
                component={data.components[key]}
                expanded={expanded === key}
                onToggle={() => setExpanded(expanded === key ? null : key)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
