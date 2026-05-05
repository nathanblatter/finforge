import { useState, useMemo } from 'react'
import { formatCurrency, formatDate } from '../../utils/format'
import type { TransactionResponse } from '../../types'

interface Props {
  transactions: TransactionResponse[]
}

export default function TransactionFeed({ transactions }: Props) {
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [hidePending, setHidePending] = useState(false)

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
                    {t.category ?? '—'}
                    {t.subcategory && (
                      <span className="text-slate-600 text-xs ml-1">· {t.subcategory}</span>
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
