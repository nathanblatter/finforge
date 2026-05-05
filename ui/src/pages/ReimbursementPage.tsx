import { useState, useMemo, useEffect } from 'react'
import { useReimbursementTransactions } from '../hooks/useReimbursement'
import { api } from '../api/client'
import Header from '../components/layout/Header'
import { formatCurrency, formatDate } from '../utils/format'

interface ReimbursementTxn {
  id: string
  date: string
  amount: number
  merchant_name: string | null
  category: string | null
  subcategory: string | null
  account_alias: string
  tier: string
  auto_selected: boolean
}

const HARD_CAP = 1500
const COOKIE_KEY = 'finforge_reimburse_categories'

function loadCategoryPrefs(): Set<string> | null {
  try {
    const raw = document.cookie.split('; ').find(c => c.startsWith(COOKIE_KEY + '='))
    if (!raw) return null
    const val = decodeURIComponent(raw.split('=')[1])
    return new Set(JSON.parse(val) as string[])
  } catch { return null }
}

function saveCategoryPrefs(cats: Set<string>) {
  const val = JSON.stringify(Array.from(cats))
  document.cookie = `${COOKIE_KEY}=${encodeURIComponent(val)}; path=/; max-age=${60 * 60 * 24 * 365}`
}

function MonthSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const months: { label: string; value: string }[] = []
  const now = new Date()
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    months.push({ label, value: val })
  }
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
    >
      {months.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}

function TierBadge({ tier }: { tier: string }) {
  const styles: Record<string, string> = {
    always: 'bg-emerald-500/20 text-emerald-400',
    limited: 'bg-yellow-500/20 text-yellow-400',
    never: 'bg-slate-600/30 text-slate-500',
  }
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${styles[tier] || styles.never}`}>
      {tier}
    </span>
  )
}

export default function ReimbursementPage() {
  const now = new Date()
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

  const [month, setMonth] = useState(defaultMonth)
  const [rentAmount, setRentAmount] = useState(750)
  const [miscTarget, setMiscTarget] = useState(500)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [enabledCategories, setEnabledCategories] = useState<Set<string>>(new Set())
  const [categoriesInitialized, setCategoriesInitialized] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [emailing, setEmailing] = useState(false)
  const [emailSent, setEmailSent] = useState(false)
  const [verbose, setVerbose] = useState(false)

  const { data, isLoading } = useReimbursementTransactions(month, rentAmount, miscTarget)

  // When data loads, initialize selectedIds from auto_selected
  useEffect(() => {
    if (data?.transactions) {
      const autoSelected = new Set<string>()
      data.transactions.forEach((t: ReimbursementTxn) => {
        if (t.auto_selected) autoSelected.add(t.id)
      })
      setSelectedIds(autoSelected)
    }
  }, [data])

  const transactions: ReimbursementTxn[] = data?.transactions || []

  const categories = useMemo(() => {
    const set = new Set<string>()
    transactions.forEach(t => { if (t.category) set.add(t.category) })
    return Array.from(set).sort()
  }, [transactions])

  // Initialize enabledCategories from cookie or default to all
  useEffect(() => {
    if (categories.length === 0 || categoriesInitialized) return
    const saved = loadCategoryPrefs()
    if (saved) {
      // Only keep categories that actually exist in current data
      const valid = new Set(categories.filter(c => saved.has(c)))
      setEnabledCategories(valid.size > 0 ? valid : new Set(categories))
    } else {
      setEnabledCategories(new Set(categories))
    }
    setCategoriesInitialized(true)
  }, [categories, categoriesInitialized])

  function toggleCategory(cat: string) {
    setEnabledCategories(prev => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      saveCategoryPrefs(next)
      return next
    })
  }

  function toggleAllCategories() {
    setEnabledCategories(prev => {
      const next = prev.size === categories.length ? new Set<string>() : new Set(categories)
      saveCategoryPrefs(next)
      return next
    })
  }

  const filtered = useMemo(() => {
    return transactions.filter(t => {
      if (t.category && !enabledCategories.has(t.category)) return false
      if (!t.category && enabledCategories.size < categories.length) return false
      if (search) {
        const q = search.toLowerCase()
        return (
          t.merchant_name?.toLowerCase().includes(q) ||
          t.category?.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [transactions, search, enabledCategories, categories])

  const selectedTotal = useMemo(() => {
    return transactions
      .filter(t => selectedIds.has(t.id))
      .reduce((sum, t) => sum + t.amount, 0)
  }, [transactions, selectedIds])

  const grandTotal = rentAmount + selectedTotal
  const overCap = grandTotal > HARD_CAP

  // Category breakdown of selected
  const breakdown = useMemo(() => {
    const map = new Map<string, number>()
    transactions
      .filter(t => selectedIds.has(t.id))
      .forEach(t => {
        const cat = t.category || 'Other'
        map.set(cat, (map.get(cat) || 0) + t.amount)
      })
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [transactions, selectedIds])

  function toggleId(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (selectedIds.size === filtered.length) {
      // Deselect all visible
      setSelectedIds(prev => {
        const next = new Set(prev)
        filtered.forEach(t => next.delete(t.id))
        return next
      })
    } else {
      // Select all visible
      setSelectedIds(prev => {
        const next = new Set(prev)
        filtered.forEach(t => next.add(t.id))
        return next
      })
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      await api.exportReimbursement({
        transaction_ids: Array.from(selectedIds),
        rent_amount: rentAmount,
        month,
        verbose,
      })
    } catch (err: any) {
      alert(err.message)
    } finally {
      setExporting(false)
    }
  }

  async function handleEmail() {
    setEmailing(true)
    setEmailSent(false)
    try {
      await api.emailReimbursement({
        transaction_ids: Array.from(selectedIds),
        rent_amount: rentAmount,
        month,
        verbose,
      })
      setEmailSent(true)
      setTimeout(() => setEmailSent(false), 5000)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setEmailing(false)
    }
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div className="flex items-center justify-between">
        <Header title="Reimbursement" />
        <MonthSelector value={month} onChange={setMonth} />
      </div>

      {/* Config bar */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Rent Amount</label>
            <div className="flex items-center">
              <span className="text-slate-500 text-sm mr-1">$</span>
              <input
                type="number"
                value={rentAmount}
                onChange={e => setRentAmount(Number(e.target.value) || 0)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Misc Target</label>
            <div className="flex items-center">
              <span className="text-slate-500 text-sm mr-1">$</span>
              <input
                type="number"
                value={miscTarget}
                onChange={e => setMiscTarget(Number(e.target.value) || 0)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Selected Misc</label>
            <div className="text-2xl font-bold text-sky-400">{formatCurrency(selectedTotal)}</div>
            <div className="text-xs text-slate-500">{selectedIds.size} transactions</div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Grand Total</label>
            <div className={`text-2xl font-bold ${overCap ? 'text-rose-400' : 'text-emerald-400'}`}>
              {formatCurrency(grandTotal)}
            </div>
            <div className="text-xs text-slate-500">
              cap: {formatCurrency(HARD_CAP)}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4">
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>$0</span>
            <span>{formatCurrency(HARD_CAP)}</span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${overCap ? 'bg-rose-500' : 'bg-emerald-500'}`}
              style={{ width: `${Math.min((grandTotal / HARD_CAP) * 100, 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Transaction table */}
        <div className="lg:col-span-3 bg-slate-800 border border-slate-700 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-300">Transactions</h3>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={verbose}
                  onChange={e => setVerbose(e.target.checked)}
                  className="accent-sky-500"
                />
                Verbose
              </label>
              <button
                onClick={handleExport}
                disabled={exporting || selectedIds.size === 0}
                className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
              >
                {exporting ? 'Generating...' : 'Download'}
              </button>
              <button
                onClick={handleEmail}
                disabled={emailing || selectedIds.size === 0}
                className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                  emailSent
                    ? 'bg-emerald-600'
                    : 'bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500'
                }`}
              >
                {emailing ? 'Sending...' : emailSent ? 'Sent!' : 'Email Dad'}
              </button>
            </div>
          </div>

          {/* Filters */}
          <div className="space-y-3 mb-4">
            <input
              type="text"
              placeholder="Search merchant..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            <div className="flex flex-wrap gap-2 items-center">
              <button
                onClick={toggleAllCategories}
                className="text-xs text-sky-400 hover:text-sky-300 transition-colors mr-1"
              >
                {enabledCategories.size === categories.length ? 'Deselect all' : 'Select all'}
              </button>
              {categories.map(cat => (
                <label
                  key={cat}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs cursor-pointer transition-colors ${
                    enabledCategories.has(cat)
                      ? 'bg-sky-600/20 text-sky-300 border border-sky-500/30'
                      : 'bg-slate-900 text-slate-500 border border-slate-700'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={enabledCategories.has(cat)}
                    onChange={() => toggleCategory(cat)}
                    className="sr-only"
                  />
                  {cat}
                </label>
              ))}
            </div>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="h-10 bg-slate-700 animate-pulse rounded-lg" />
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                    <th className="pb-2 pr-2 w-8">
                      <input
                        type="checkbox"
                        checked={filtered.length > 0 && filtered.every(t => selectedIds.has(t.id))}
                        onChange={toggleAll}
                        className="accent-sky-500"
                      />
                    </th>
                    <th className="pb-2 pr-3 w-16">Tier</th>
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
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        No transactions found
                      </td>
                    </tr>
                  ) : (
                    filtered.map(t => (
                      <tr
                        key={t.id}
                        onClick={() => toggleId(t.id)}
                        className={`cursor-pointer transition-colors ${
                          selectedIds.has(t.id) ? 'bg-sky-950/30 hover:bg-sky-950/40' : 'hover:bg-slate-700/30'
                        }`}
                      >
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(t.id)}
                            onChange={() => toggleId(t.id)}
                            onClick={e => e.stopPropagation()}
                            className="accent-sky-500"
                          />
                        </td>
                        <td className="py-2 pr-3"><TierBadge tier={t.tier} /></td>
                        <td className="py-2 pr-4 text-slate-400 whitespace-nowrap">{formatDate(t.date)}</td>
                        <td className="py-2 pr-4 text-slate-200">{t.merchant_name || 'Unknown'}</td>
                        <td className="py-2 pr-4 text-slate-400">
                          {t.category || '—'}
                          {t.subcategory && <span className="text-slate-600 text-xs ml-1">· {t.subcategory}</span>}
                        </td>
                        <td className="py-2 pr-4 text-slate-400">{t.account_alias}</td>
                        <td className="py-2 text-right font-medium text-slate-100">{formatCurrency(t.amount)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-3 text-xs text-slate-600">
            {filtered.length} transactions · {selectedIds.size} selected
          </div>
        </div>

        {/* Summary sidebar */}
        <div className="space-y-4">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Breakdown</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Rent</span>
                <span className="text-slate-100 font-medium">{formatCurrency(rentAmount)}</span>
              </div>
              <div className="border-t border-slate-700 my-2" />
              {breakdown.map(([cat, total]) => (
                <div key={cat} className="flex justify-between text-sm">
                  <span className="text-slate-400">{cat}</span>
                  <span className="text-slate-100 font-medium">{formatCurrency(total)}</span>
                </div>
              ))}
              {breakdown.length === 0 && (
                <div className="text-xs text-slate-500">No transactions selected</div>
              )}
              <div className="border-t border-slate-700 my-2" />
              <div className="flex justify-between text-sm font-semibold">
                <span className="text-slate-300">Total</span>
                <span className={overCap ? 'text-rose-400' : 'text-emerald-400'}>
                  {formatCurrency(grandTotal)}
                </span>
              </div>
            </div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Tier Rules</h3>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <TierBadge tier="always" />
                <span className="text-slate-400">Gas, Groceries, Education</span>
              </div>
              <div className="flex items-center gap-2">
                <TierBadge tier="limited" />
                <span className="text-slate-400">Fast food (max 6/mo)</span>
              </div>
              <div className="flex items-center gap-2">
                <TierBadge tier="never" />
                <span className="text-slate-400">Shopping, Entertainment, etc.</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
