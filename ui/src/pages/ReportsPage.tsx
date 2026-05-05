import { useState, useMemo } from 'react'
import { useFinancialPreview, useTithingIncome, useContributionPreview } from '../hooks/useReports'
import { useDownloadQueue } from '../hooks/useDownloadQueue'
import { api } from '../api/client'
import Header from '../components/layout/Header'
import { formatCurrency, formatDate } from '../utils/format'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'
const TOKEN_KEY = 'finforge_token'

type Period = 'monthly' | 'quarterly' | 'annual' | 'custom'
type Tab = 'financial' | 'tithing' | 'contributions'

interface InKindDonation {
  id: string
  symbol: string
  shares: string
  fmv: string
}

interface TithingTransaction {
  id: string
  date: string
  merchant_name: string | null
  category: string | null
  amount: number
  auto_checked: boolean
  auto_excluded: boolean
}

// ── Helpers ──────────────────────────────────────────────────

function generateOptions(period: Period): { label: string; value: string }[] {
  const now = new Date()
  const options: { label: string; value: string }[] = []

  if (period === 'monthly') {
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      const label = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
      options.push({ label, value: val })
    }
  } else if (period === 'quarterly') {
    // Current quarter and previous 6
    const currentQ = Math.floor(now.getMonth() / 3) + 1
    const currentYear = now.getFullYear()
    for (let i = 0; i < 7; i++) {
      let q = currentQ - i
      let y = currentYear
      while (q <= 0) { q += 4; y-- }
      const shortYear = String(y).slice(2)
      // Value: YYYY-MM of the last month in the quarter (for API resolution)
      const lastMonth = q * 3
      const val = `${y}-${String(lastMonth).padStart(2, '0')}`
      options.push({ label: `Q${q} '${shortYear}`, value: val })
    }
  } else if (period === 'annual') {
    // This year + previous 2
    for (let i = 0; i < 3; i++) {
      const y = now.getFullYear() - i
      options.push({ label: `${y}`, value: `${y}-12` })
    }
  }

  return options
}

function buildAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

async function fetchReportBlob(endpoint: string, body: Record<string, unknown>): Promise<Blob> {
  const res = await fetch(`${BASE}${endpoint}`, {
    method: 'POST',
    headers: buildAuthHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Report generation failed: ${res.status}`)
  return res.blob()
}

// ── Sub-components ───────────────────────────────────────────

function PeriodSelector({ period, value, onChange }: { period: Period; value: string; onChange: (v: string) => void }) {
  const options = useMemo(() => generateOptions(period), [period])

  // If current value isn't in the new options, reset to the first one
  const validValue = options.some(o => o.value === value) ? value : options[0]?.value ?? ''
  if (validValue !== value && validValue) {
    // Schedule the reset for next tick to avoid setState during render
    setTimeout(() => onChange(validValue), 0)
  }

  return (
    <select
      value={validValue}
      onChange={(e) => onChange(e.target.value)}
      className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
    >
      {options.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}

function PeriodPills({ value, onChange }: { value: Period; onChange: (v: Period) => void }) {
  const options: { label: string; value: Period }[] = [
    { label: 'Monthly', value: 'monthly' },
    { label: 'Quarterly', value: 'quarterly' },
    { label: 'Annual', value: 'annual' },
    { label: 'Custom', value: 'custom' },
  ]
  return (
    <div className="flex gap-1 bg-slate-900 rounded-lg p-1">
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            value === o.value
              ? 'bg-sky-600 text-white'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function TabBar({ value, onChange }: { value: Tab; onChange: (v: Tab) => void }) {
  const tabs: { label: string; value: Tab }[] = [
    { label: 'Financial', value: 'financial' },
    { label: 'Tithing', value: 'tithing' },
    { label: 'Contributions', value: 'contributions' },
  ]
  return (
    <div className="flex gap-1 border-b border-slate-700">
      {tabs.map(t => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
            value === t.value
              ? 'border-sky-500 text-sky-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function PreviewCard({ label, value, color = 'text-slate-100' }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  )
}

function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {[...Array(count)].map((_, i) => (
        <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-5">
          <div className="h-3 w-20 bg-slate-700 animate-pulse rounded mb-2" />
          <div className="h-7 w-28 bg-slate-700 animate-pulse rounded" />
        </div>
      ))}
    </div>
  )
}

function SkeletonTable() {
  return (
    <div className="space-y-2">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="h-10 bg-slate-700 animate-pulse rounded-lg" />
      ))}
    </div>
  )
}

// ── Financial Tab ────────────────────────────────────────────

function FinancialTab({ period, month, startDate, endDate }: {
  period: string; month: string; startDate?: string; endDate?: string
}) {
  const { data, isLoading } = useFinancialPreview(period, month, startDate, endDate)
  const { addJob } = useDownloadQueue()
  const [emailing, setEmailing] = useState(false)
  const [emailSent, setEmailSent] = useState(false)

  function handleGenerate() {
    const body = { period, month, start_date: startDate, end_date: endDate }
    addJob(`Financial Report - ${month}`, () => fetchReportBlob('/reports/financial/generate', body))
  }

  async function handleEmail() {
    setEmailing(true)
    setEmailSent(false)
    try {
      await api.emailFinancialReport({ period, month, start_date: startDate, end_date: endDate })
      setEmailSent(true)
      setTimeout(() => setEmailSent(false), 5000)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setEmailing(false)
    }
  }

  if (isLoading) return <SkeletonCards />

  const preview = data || {}

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <PreviewCard
          label="Net Worth"
          value={formatCurrency(preview.net_worth ?? 0)}
          color="text-sky-400"
        />
        <PreviewCard
          label="Liquid Cash"
          value={formatCurrency(preview.liquid_cash ?? 0)}
          color="text-emerald-400"
        />
        <PreviewCard
          label="Savings"
          value={formatCurrency(preview.savings ?? 0)}
          color="text-violet-400"
        />
        <PreviewCard
          label="CC Debt"
          value={formatCurrency(preview.cc_debt ?? 0)}
          color={Number(preview.cc_debt ?? 0) > 0 ? 'text-rose-400' : 'text-emerald-400'}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleGenerate}
          className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
        >
          Generate PDF
        </button>
        <button
          onClick={handleEmail}
          disabled={emailing}
          className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
            emailSent
              ? 'bg-emerald-600'
              : 'bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500'
          }`}
        >
          {emailing ? 'Sending...' : emailSent ? 'Sent!' : 'Email Report'}
        </button>
      </div>
    </div>
  )
}

// ── Tithing Tab ──────────────────────────────────────────────

function TithingTab({ period, month, startDate, endDate }: {
  period: string; month: string; startDate?: string; endDate?: string
}) {
  const { data, isLoading } = useTithingIncome(period, month, startDate, endDate)
  const { addJob } = useDownloadQueue()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [initialized, setInitialized] = useState(false)
  const [inKindDonations, setInKindDonations] = useState<InKindDonation[]>([])
  const [newSymbol, setNewSymbol] = useState('')
  const [newShares, setNewShares] = useState('')
  const [newFmv, setNewFmv] = useState('')
  const [emailing, setEmailing] = useState(false)
  const [emailSent, setEmailSent] = useState(false)

  const transactions: TithingTransaction[] = data?.income_transactions ?? []

  // Auto-select BYU rows on first load
  if (transactions.length > 0 && !initialized) {
    const autoIds = new Set<string>()
    transactions.forEach(t => {
      if (t.auto_checked) autoIds.add(t.id)
    })
    setSelectedIds(autoIds)
    setInitialized(true)
  }

  const totalIncome = useMemo(() => {
    return transactions
      .filter(t => selectedIds.has(t.id))
      .reduce((sum, t) => sum + Number(t.amount), 0)
  }, [transactions, selectedIds])

  const tithingTarget = totalIncome * 0.1

  function toggleId(id: string) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    const selectable = transactions.filter(t => !t.is_dad_transfer)
    if (selectable.every(t => selectedIds.has(t.id))) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(selectable.map(t => t.id)))
    }
  }

  function addInKindDonation() {
    if (!newSymbol.trim() || !newShares.trim() || !newFmv.trim()) return
    setInKindDonations(prev => [
      ...prev,
      { id: `ink-${Date.now()}`, symbol: newSymbol.toUpperCase().trim(), shares: newShares.trim(), fmv: newFmv.trim() },
    ])
    setNewSymbol('')
    setNewShares('')
    setNewFmv('')
  }

  function removeInKindDonation(id: string) {
    setInKindDonations(prev => prev.filter(d => d.id !== id))
  }

  function handleGenerate() {
    const body = {
      period, month,
      start_date: startDate, end_date: endDate,
      selected_transaction_ids: Array.from(selectedIds),
      in_kind_donations: inKindDonations.map(d => ({
        symbol: d.symbol, shares: Number(d.shares), fmv: Number(d.fmv),
      })),
    }
    addJob(`Tithing Report - ${month}`, () => fetchReportBlob('/reports/tithing/generate', body))
  }

  async function handleEmail() {
    setEmailing(true)
    setEmailSent(false)
    try {
      await api.emailTithingReport({
        period, month,
        start_date: startDate, end_date: endDate,
        selected_transaction_ids: Array.from(selectedIds),
        in_kind_donations: inKindDonations.map(d => ({
          symbol: d.symbol, shares: Number(d.shares), fmv: Number(d.fmv),
        })),
      })
      setEmailSent(true)
      setTimeout(() => setEmailSent(false), 5000)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setEmailing(false)
    }
  }

  if (isLoading) return <SkeletonTable />

  return (
    <div className="space-y-6">
      {/* Transaction table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Income Transactions</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-2 w-8">
                  <input
                    type="checkbox"
                    checked={
                      transactions.filter(t => !t.is_dad_transfer).length > 0 &&
                      transactions.filter(t => !t.is_dad_transfer).every(t => selectedIds.has(t.id))
                    }
                    onChange={toggleAll}
                    className="accent-sky-500"
                  />
                </th>
                <th className="pb-2 pr-4">Date</th>
                <th className="pb-2 pr-4">Merchant</th>
                <th className="pb-2 pr-4">Account</th>
                <th className="pb-2 text-right">Amount</th>
                <th className="pb-2 pl-3 w-24"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500">
                    No income transactions found
                  </td>
                </tr>
              ) : (
                transactions.map(t => {
                  const isDad = t.auto_excluded
                  const isByu = t.auto_checked
                  return (
                    <tr
                      key={t.id}
                      onClick={() => !isDad && toggleId(t.id)}
                      className={`transition-colors ${
                        isDad
                          ? 'opacity-50 cursor-default'
                          : selectedIds.has(t.id)
                            ? 'bg-sky-950/30 hover:bg-sky-950/40 cursor-pointer'
                            : 'hover:bg-slate-700/30 cursor-pointer'
                      }`}
                    >
                      <td className="py-2 pr-2">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(t.id)}
                          disabled={isDad}
                          onChange={() => toggleId(t.id)}
                          onClick={e => e.stopPropagation()}
                          className="accent-sky-500 disabled:opacity-30"
                        />
                      </td>
                      <td className="py-2 pr-4 text-slate-400 whitespace-nowrap">{formatDate(t.date)}</td>
                      <td className="py-2 pr-4 text-slate-200">{t.merchant_name || 'Unknown'}</td>
                      <td className="py-2 pr-4 text-slate-400">{t.account_alias}</td>
                      <td className="py-2 text-right font-medium text-slate-100">{formatCurrency(t.amount)}</td>
                      <td className="py-2 pl-3">
                        {isByu && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">
                            BYU
                          </span>
                        )}
                        {isDad && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-600/30 text-slate-500">
                            Excluded
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* In-kind donations */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">In-Kind Donations</h3>
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Symbol</label>
            <input
              type="text"
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value)}
              placeholder="AAPL"
              className="w-24 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Shares</label>
            <input
              type="text"
              value={newShares}
              onChange={e => setNewShares(e.target.value)}
              placeholder="10"
              className="w-24 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">FMV ($)</label>
            <input
              type="text"
              value={newFmv}
              onChange={e => setNewFmv(e.target.value)}
              placeholder="1500.00"
              className="w-32 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
          <button
            onClick={addInKindDonation}
            disabled={!newSymbol.trim() || !newShares.trim() || !newFmv.trim()}
            className="px-3 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
          >
            + Add
          </button>
        </div>
        {inKindDonations.length > 0 && (
          <div className="space-y-2">
            {inKindDonations.map(d => (
              <div key={d.id} className="flex items-center gap-4 bg-slate-900 rounded-lg px-4 py-2 text-sm">
                <span className="text-sky-400 font-medium w-16">{d.symbol}</span>
                <span className="text-slate-300">{d.shares} shares</span>
                <span className="text-slate-300">FMV: {formatCurrency(Number(d.fmv))}</span>
                <button
                  onClick={() => removeInKindDonation(d.id)}
                  className="ml-auto text-slate-500 hover:text-rose-400 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Summary */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Tithing Summary</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-slate-400 mb-1">Total Income</div>
            <div className="text-2xl font-bold text-emerald-400">{formatCurrency(totalIncome)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400 mb-1">10% Target</div>
            <div className="text-2xl font-bold text-sky-400">{formatCurrency(tithingTarget)}</div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleGenerate}
          className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
        >
          Generate PDF
        </button>
        <button
          onClick={handleEmail}
          disabled={emailing}
          className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
            emailSent
              ? 'bg-emerald-600'
              : 'bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500'
          }`}
        >
          {emailing ? 'Sending...' : emailSent ? 'Sent!' : 'Email Report'}
        </button>
      </div>
    </div>
  )
}

// ── Contributions Tab ────────────────────────────────────────

function ContributionsTab({ period, month, startDate, endDate }: {
  period: string; month: string; startDate?: string; endDate?: string
}) {
  const { data, isLoading } = useContributionPreview(period, month, startDate, endDate)
  const { addJob } = useDownloadQueue()
  const [emailing, setEmailing] = useState(false)
  const [emailSent, setEmailSent] = useState(false)

  const preview = data || {}
  const transfers = preview.transfers ?? []
  const ROTH_LIMIT = 7000

  function handleGenerate() {
    const body = { period, month, start_date: startDate, end_date: endDate }
    addJob(`Contributions Report - ${month}`, () => fetchReportBlob('/reports/contributions/generate', body))
  }

  async function handleEmail() {
    setEmailing(true)
    setEmailSent(false)
    try {
      await api.emailContributionReport({ period, month, start_date: startDate, end_date: endDate })
      setEmailSent(true)
      setTimeout(() => setEmailSent(false), 5000)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setEmailing(false)
    }
  }

  if (isLoading) return <SkeletonCards />

  const rothHeadroom = ROTH_LIMIT - Number(preview.roth_contributed ?? 0)

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <PreviewCard
          label="Total Contributions"
          value={formatCurrency(preview.total_contributions ?? 0)}
          color="text-sky-400"
        />
        <PreviewCard
          label="Dad's Share"
          value={formatCurrency(preview.dads_share ?? 0)}
          color="text-violet-400"
        />
        <PreviewCard
          label="Nathan's Share"
          value={formatCurrency(preview.nathans_share ?? 0)}
          color="text-emerald-400"
        />
        <PreviewCard
          label="Roth IRA Headroom"
          value={formatCurrency(rothHeadroom)}
          color={rothHeadroom > 0 ? 'text-amber-400' : 'text-rose-400'}
        />
      </div>

      {/* Transfer table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Contribution Transfers</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-4">Date</th>
                <th className="pb-2 pr-4">Description</th>
                <th className="pb-2 pr-4">From</th>
                <th className="pb-2 pr-4">To</th>
                <th className="pb-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {transfers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-500">
                    No contribution transfers found
                  </td>
                </tr>
              ) : (
                transfers.map((t: any, i: number) => (
                  <tr key={t.id ?? i} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-2 pr-4 text-slate-400 whitespace-nowrap">{formatDate(t.date)}</td>
                    <td className="py-2 pr-4 text-slate-200">{t.description || t.merchant_name || 'Transfer'}</td>
                    <td className="py-2 pr-4 text-slate-400">{t.from_account || '—'}</td>
                    <td className="py-2 pr-4 text-slate-400">{t.to_account || '—'}</td>
                    <td className="py-2 text-right font-medium text-slate-100">{formatCurrency(t.amount)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleGenerate}
          className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
        >
          Generate PDF
        </button>
        <button
          onClick={handleEmail}
          disabled={emailing}
          className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
            emailSent
              ? 'bg-emerald-600'
              : 'bg-violet-600 hover:bg-violet-500 disabled:bg-slate-700 disabled:text-slate-500'
          }`}
        >
          {emailing ? 'Sending...' : emailSent ? 'Sent!' : 'Email Report'}
        </button>
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function ReportsPage() {
  const now = new Date()
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`

  const [tab, setTab] = useState<Tab>('financial')
  const [period, setPeriod] = useState<Period>('monthly')
  const [month, setMonth] = useState(defaultMonth)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const customStart = period === 'custom' ? startDate : undefined
  const customEnd = period === 'custom' ? endDate : undefined

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div className="flex items-center justify-between">
        <Header title="Reports" />
      </div>

      {/* Config bar */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="flex flex-wrap items-center gap-4">
          <PeriodPills value={period} onChange={setPeriod} />
          {period !== 'custom' && (
            <PeriodSelector period={period} value={month} onChange={setMonth} />
          )}
          {period === 'custom' && (
            <>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <TabBar value={tab} onChange={setTab} />

      {/* Tab content */}
      <div className="pb-14">
        {tab === 'financial' && (
          <FinancialTab period={period} month={month} startDate={customStart} endDate={customEnd} />
        )}
        {tab === 'tithing' && (
          <TithingTab period={period} month={month} startDate={customStart} endDate={customEnd} />
        )}
        {tab === 'contributions' && (
          <ContributionsTab period={period} month={month} startDate={customStart} endDate={customEnd} />
        )}
      </div>
    </div>
  )
}
