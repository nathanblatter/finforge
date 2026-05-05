import type { Summary } from '../../types'
import { formatCurrency } from '../../utils/format'
import MetricCard from './MetricCard'

interface KeyMetricsProps {
  summary: Summary
}

export default function KeyMetrics({ summary }: KeyMetricsProps) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        label="Net Worth"
        value={formatCurrency(summary.net_worth)}
        subtitle={`As of ${summary.as_of}`}
        accentColor={summary.net_worth >= 0 ? 'text-emerald-400' : 'text-rose-400'}
      />
      {/* PRD: label must be "Savings (Brokerage)" to reinforce mental model */}
      <MetricCard
        label="Savings (Brokerage)"
        value={formatCurrency(summary.savings_balance)}
        subtitle="Schwab Brokerage"
        accentColor="text-sky-400"
      />
      <MetricCard
        label="Liquid Cash"
        value={formatCurrency(summary.liquid_cash)}
        subtitle="WF Checking"
        accentColor="text-slate-300"
      />
      <MetricCard
        label="CC Balance Owed"
        value={formatCurrency(summary.cc_balance_owed)}
        subtitle="WF CC + Amex"
        accentColor="text-amber-400"
      />
    </div>
  )
}
