import { formatCurrency } from '../../utils/format'
import type { MonthlySpendingResponse } from '../../types'

interface Props {
  data: MonthlySpendingResponse
}

export default function SpendSummary({ data }: Props) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
          Discretionary
        </div>
        <div className="text-2xl font-bold text-sky-400">
          {formatCurrency(data.total_discretionary)}
        </div>
        <div className="text-xs text-slate-500 mt-1">excl. fixed expenses</div>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
          Fixed Expenses
        </div>
        <div className="text-2xl font-bold text-amber-400">
          {formatCurrency(data.fixed_expenses.total)}
        </div>
        <div className="text-xs text-slate-500 mt-1">rent + tuition</div>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
          Total Spent
        </div>
        <div className="text-2xl font-bold text-slate-100">
          {formatCurrency(Number(data.total_discretionary) + Number(data.fixed_expenses.total))}
        </div>
        <div className="text-xs text-slate-500 mt-1">{data.transaction_count} transactions</div>
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
          Categories
        </div>
        <div className="text-2xl font-bold text-slate-100">
          {data.by_category.length}
        </div>
        <div className="text-xs text-slate-500 mt-1">unique categories</div>
      </div>
    </div>
  )
}
