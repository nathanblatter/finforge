import { formatCurrency } from '../../utils/format'
import type { FixedExpenses } from '../../types'

interface Props {
  data: FixedExpenses
}

export default function FixedExpensesPanel({ data }: Props) {
  return (
    <div className="bg-slate-800 border border-amber-500/30 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-sm font-semibold text-amber-400">Fixed Expenses</h3>
        <span className="text-xs text-amber-500/70 bg-amber-500/10 px-2 py-0.5 rounded-full">
          excluded from discretionary
        </span>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Rent and tuition are tracked separately and not counted in category breakdowns.
      </p>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-400">Rent</span>
          <span className="text-sm font-medium text-amber-300">{formatCurrency(data.rent)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-400">Tuition</span>
          <span className="text-sm font-medium text-amber-300">{formatCurrency(data.tuition)}</span>
        </div>
        <div className="border-t border-slate-700 pt-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-slate-300">Total Fixed</span>
          <span className="text-sm font-bold text-amber-400">{formatCurrency(data.total)}</span>
        </div>
      </div>
    </div>
  )
}
