import { useState, useMemo } from 'react'
import { formatCurrency, formatDate } from '../../utils/format'
import { useRecategorize, useCreateCategoryRule } from '../../hooks/useSpending'
import { useToast } from '../Toast'
import type { TransactionResponse } from '../../types'

interface Props {
  transactions: TransactionResponse[]
}

export default function TransactionFeed({ transactions }: Props) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [hidePending, setHidePending] = useState(false)

  const recategorize = useRecategorize()
  const createRule = useCreateCategoryRule()
  const toast = useToast()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [applyRule, setApplyRule] = useState(false)

  const startEdit = (t: TransactionResponse) => {
    setEditingId(t.id)
    setEditValue(t.category ?? '')
    setApplyRule(false)
  }

  const saveEdit = (t: TransactionResponse) => {
    const val = editValue.trim()
    if (!val) { toast.error('Enter a category'); return }
    setEditingId(null)
    if (applyRule && t.merchant_name) {
      createRule.mutate(
        { merchant: t.merchant_name, category: val },
        {
          onSuccess: () => toast.success(`All "${t.merchant_name}" → ${val}`),
          onError: (e: any) => toast.error(e?.message ?? 'Failed to save rule'),
        },
      )
    } else {
      recategorize.mutate(
        { id: t.id, category: val },
        {
          onSuccess: () => toast.success(`Recategorized to ${val}`),
          onError: (e: any) => toast.error(e?.message ?? 'Failed to recategorize'),
        },
      )
    }
  }

  const categories = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach((t) => { if (t.category) set.add(t.category) })
    return Array.from(set).sort()
  }, [transactions])

  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      if (hidePending && t.is_pending) return false
      if (categoryFilter && t.category !== categoryFilter) return false
      if (search) {
        const q = search.toLowerCase()
        return (
          t.merchant_name?.toLowerCase().includes(q) ||
          t.category?.toLowerCase().includes(q) ||
          t.account_alias.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [transactions, search, categoryFilter, hidePending])

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Transactions</h3>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="Search merchant, category…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={hidePending}
            onChange={(e) => setHidePending(e.target.checked)}
            className="accent-sky-500"
          />
          Hide pending
        </label>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
              <th className="pb-2 pr-4">Date</th>
              <th className="pb-2 pr-4">Merchant</th>
              <th className="pb-2 pr-4">Category</th>
              <th className="pb-2 pr-4">Account</th>
              <th className="pb-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-slate-500">
                  No transactions match your filters
                </td>
              </tr>
            ) : (
              filtered.map((t) => (
                <tr key={t.id} className="hover:bg-slate-700/30 transition-colors">
                  <td className="py-2.5 pr-4 text-slate-400 whitespace-nowrap">
                    {formatDate(t.date)}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-200">
                    <div className="flex items-center gap-2">
                      {t.merchant_name ?? <span className="text-slate-500 italic">Unknown</span>}
                      {t.is_pending && (
                        <span className="text-xs bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded">
                          Pending
                        </span>
                      )}
                      {t.is_fixed_expense && (
                        <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">
                          Fixed
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4 text-slate-400">
                    {editingId === t.id ? (
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center gap-1.5">
                          <input
                            autoFocus
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveEdit(t)
                              if (e.key === 'Escape') setEditingId(null)
                            }}
                            className="w-32 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
                          />
                          <button onClick={() => saveEdit(t)} className="text-xs text-sky-400 hover:text-sky-300">Save</button>
                          <button onClick={() => setEditingId(null)} className="text-xs text-slate-500 hover:text-slate-300">Cancel</button>
                        </div>
                        {t.merchant_name && (
                          <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                            <input type="checkbox" checked={applyRule} onChange={(e) => setApplyRule(e.target.checked)} className="accent-sky-500" />
                            Always for "{t.merchant_name}"
                          </label>
                        )}
                      </div>
                    ) : (
                      <button
                        onClick={() => startEdit(t)}
                        title="Click to recategorize"
                        className="group inline-flex items-center gap-1 hover:text-slate-200 transition-colors"
                      >
                        <span>{t.category ?? '—'}</span>
                        {t.category_overridden && (
                          <span className="w-1.5 h-1.5 rounded-full bg-sky-500" title="Manually set" />
                        )}
                        {t.subcategory && (
                          <span className="text-slate-600 text-xs">· {t.subcategory}</span>
                        )}
                        <svg className="opacity-0 group-hover:opacity-100 transition-opacity" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                        </svg>
                      </button>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-slate-400">{t.account_alias}</td>
                  <td className="py-2.5 text-right font-medium">
                    <span className={t.amount < 0 ? 'text-emerald-400' : 'text-slate-100'}>
                      {formatCurrency(Math.abs(t.amount))}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-xs text-slate-600">
        Showing {filtered.length} of {transactions.length} transactions
      </div>
    </div>
  )
}
