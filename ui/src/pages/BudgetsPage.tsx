import { useMemo, useState } from 'react'
import Header from '../components/layout/Header'
import ConfirmDialog from '../components/ConfirmDialog'
import { useToast } from '../components/Toast'
import { useBudgets, useUpsertBudget, useDeleteBudget } from '../hooks/useBudgets'
import { useMonthlySpending } from '../hooks/useSpending'
import { formatCurrency } from '../utils/format'
import type { BudgetItem } from '../types'

const STATUS_BAR: Record<string, string> = {
  ok: 'bg-emerald-500',
  warning: 'bg-amber-500',
  over: 'bg-rose-500',
}

const STATUS_TEXT: Record<string, string> = {
  ok: 'text-emerald-400',
  warning: 'text-amber-400',
  over: 'text-rose-400',
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function BudgetsPage() {
  const { data, isLoading } = useBudgets()
  const { data: spending } = useMonthlySpending()
  const upsert = useUpsertBudget()
  const del = useDeleteBudget()
  const toast = useToast()

  const [category, setCategory] = useState('')
  const [limit, setLimit] = useState('')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const budgets = data?.budgets ?? []

  // Category suggestions: this month's spend categories not already budgeted.
  const suggestions = useMemo(() => {
    const budgeted = new Set(budgets.map((b) => b.category))
    return (spending?.by_category ?? [])
      .map((c) => c.category)
      .filter((c) => c && !budgeted.has(c))
  }, [spending, budgets])

  const monthLabel = useMemo(() => {
    if (!data?.month) return ''
    const [y, m] = data.month.split('-')
    return new Date(Number(y), Number(m) - 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  }, [data])

  const handleSave = () => {
    const cat = category.trim()
    const amount = Number(limit)
    if (!cat) { toast.error('Pick a category'); return }
    if (!amount || amount <= 0) { toast.error('Enter a positive limit'); return }
    upsert.mutate(
      { category: cat, monthlyLimit: amount },
      {
        onSuccess: () => {
          toast.success(`Budget saved for ${cat}`)
          setCategory('')
          setLimit('')
        },
        onError: (e: any) => toast.error(e?.message ?? 'Failed to save budget'),
      },
    )
  }

  const handleDelete = () => {
    if (!pendingDelete) return
    const cat = pendingDelete
    setPendingDelete(null)
    del.mutate(cat, {
      onSuccess: () => toast.success(`Removed budget for ${cat}`),
      onError: (e: any) => toast.error(e?.message ?? 'Failed to delete budget'),
    })
  }

  const editBudget = (b: BudgetItem) => {
    setCategory(b.category)
    setLimit(String(b.monthly_limit))
  }

  return (
    <div className="space-y-6 max-w-[900px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Budgets" />
        {monthLabel && <span className="text-sm text-slate-400">{monthLabel}</span>}
      </div>

      {/* Add / edit form */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[180px]">
            <label className="block text-xs text-slate-400 mb-1">Category</label>
            <input
              list="budget-categories"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g. Groceries"
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            <datalist id="budget-categories">
              {suggestions.map((c) => <option key={c} value={c} />)}
            </datalist>
          </div>
          <div className="w-40">
            <label className="block text-xs text-slate-400 mb-1">Monthly limit</label>
            <div className="flex items-center">
              <span className="text-slate-500 text-sm mr-1">$</span>
              <input
                type="number"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                placeholder="500"
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={upsert.isPending}
            className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            {upsert.isPending ? 'Saving...' : 'Save budget'}
          </button>
        </div>
      </div>

      {/* Budget list */}
      {isLoading ? (
        <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : budgets.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No budgets yet.</p>
          <p className="text-slate-500 text-xs mt-1">Add a category limit above to start tracking.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {budgets.map((b) => (
            <div key={b.category} className="bg-slate-800 border border-slate-700 rounded-xl p-5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-baseline gap-3">
                  <span className="text-sm font-semibold text-slate-200">{b.category}</span>
                  <span className={`text-xs font-medium ${STATUS_TEXT[b.status]}`}>{b.pct.toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-slate-300">
                    {formatCurrency(b.spent)} <span className="text-slate-500">/ {formatCurrency(b.monthly_limit)}</span>
                  </span>
                  <button
                    onClick={() => editBudget(b)}
                    className="text-xs text-slate-400 hover:text-sky-400 transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setPendingDelete(b.category)}
                    aria-label={`Delete budget for ${b.category}`}
                    className="text-slate-600 hover:text-rose-400 transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${STATUS_BAR[b.status]}`}
                  style={{ width: `${Math.min(b.pct, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete budget?"
        message={<>Remove the budget for <span className="text-slate-200 font-medium">{pendingDelete}</span>?</>}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
