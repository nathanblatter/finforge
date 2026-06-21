import { useState } from 'react'
import Header from '../components/layout/Header'
import { useToast } from '../components/Toast'
import { useTaxSummary } from '../hooks/useTax'
import { api } from '../api/client'
import { formatCurrency } from '../utils/format'

const RATE_OPTIONS = [0.12, 0.22, 0.24, 0.30, 0.32, 0.35, 0.37]

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function StatCard({ label, value, tone = 'neutral', sub }: {
  label: string
  value: string
  tone?: 'neutral' | 'gain' | 'loss' | 'accent'
  sub?: string
}) {
  const toneClass = {
    neutral: 'text-slate-100',
    gain: 'text-emerald-400',
    loss: 'text-rose-400',
    accent: 'text-sky-400',
  }[tone]
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

export default function TaxCenterPage() {
  const [rate, setRate] = useState(0.30)
  const [exporting, setExporting] = useState(false)
  const { data, isLoading } = useTaxSummary(rate)
  const toast = useToast()

  const handleExport = async () => {
    setExporting(true)
    try {
      await api.exportTaxHoldings()
      toast.success('Holdings CSV downloaded')
    } catch (e: any) {
      toast.error(e?.message ?? 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const tlh = data?.tlh_opportunities ?? []
  const realized = data?.realized_activity ?? []

  return (
    <div className="space-y-6 max-w-[1000px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Tax Center" />
        <div className="flex items-center gap-3">
          <label className="text-xs text-slate-400 flex items-center gap-2">
            Marginal rate
            <select
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="bg-slate-900 border border-slate-600 rounded-lg px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
            >
              {RATE_OPTIONS.map((r) => (
                <option key={r} value={r}>{(r * 100).toFixed(0)}%</option>
              ))}
            </select>
          </label>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="px-3 py-2 text-sm font-medium bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 rounded-lg transition-colors flex items-center gap-2"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </div>

      {data?.analysis_date && (
        <p className="text-xs text-slate-500 -mt-2">
          Taxable brokerage · analysis as of {data.analysis_date} · tax year {data.tax_year}
        </p>
      )}

      {/* Hero stats */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Net unrealized G/L"
            value={formatCurrency(data?.net_unrealized_gl ?? 0)}
            tone={(data?.net_unrealized_gl ?? 0) >= 0 ? 'gain' : 'loss'}
            sub={`${formatCurrency(data?.gross_unrealized_gains ?? 0)} gains · ${formatCurrency(data?.gross_unrealized_losses ?? 0)} losses`}
          />
          <StatCard
            label="Harvestable losses"
            value={formatCurrency(data?.harvestable_loss ?? 0)}
            tone="accent"
            sub={`${tlh.length} candidate${tlh.length === 1 ? '' : 's'}${data?.wash_sale_warnings ? ` · ${data.wash_sale_warnings} wash-sale risk` : ''}`}
          />
          <StatCard
            label="Est. tax savings"
            value={formatCurrency(data?.est_tax_savings ?? 0)}
            tone="gain"
            sub={`at ${((data?.marginal_rate ?? rate) * 100).toFixed(0)}% marginal rate`}
          />
        </div>
      )}

      {/* TLH opportunities */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-200">Tax-loss harvesting opportunities</h2>
          <p className="text-xs text-slate-500 mt-0.5">Positions held at a loss in your taxable account.</p>
        </div>
        {isLoading ? (
          <div className="p-5 space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : tlh.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-400">
            No harvestable losses right now. Every position is at or above its cost basis. 🎉
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-slate-700">
                  <th className="text-left font-medium px-5 py-2.5">Symbol</th>
                  <th className="text-right font-medium px-5 py-2.5">Market value</th>
                  <th className="text-right font-medium px-5 py-2.5">Cost basis</th>
                  <th className="text-right font-medium px-5 py-2.5">Unrealized loss</th>
                  <th className="text-right font-medium px-5 py-2.5">Est. benefit</th>
                </tr>
              </thead>
              <tbody>
                {tlh.map((o) => (
                  <tr key={o.symbol} className="border-b border-slate-700/50 last:border-0">
                    <td className="px-5 py-3">
                      <span className="font-semibold text-slate-200">{o.symbol}</span>
                      {o.wash_sale_risk && (
                        <span
                          title={o.wash_sale_details ?? 'Recent purchase within the 30-day wash-sale window'}
                          className="ml-2 inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30"
                        >
                          ⚠ wash sale
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(o.market_value)}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(o.cost_basis)}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-rose-400">−{formatCurrency(o.unrealized_loss)}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-emerald-400">{formatCurrency(o.est_tax_benefit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Realized activity */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700 flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">Realized activity · {data?.tax_year ?? new Date().getFullYear()}</h2>
            <p className="text-xs text-slate-500 mt-0.5">Sells synced from Schwab orders.</p>
          </div>
          {data && (
            <span className="text-xs text-slate-400">
              {data.realized_ytd_sells} sell{data.realized_ytd_sells === 1 ? '' : 's'} · {formatCurrency(data.realized_ytd_proceeds)} proceeds
            </span>
          )}
        </div>
        {isLoading ? (
          <div className="p-5 space-y-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : realized.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-400">No sells recorded this year.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-slate-700">
                  <th className="text-left font-medium px-5 py-2.5">Symbol</th>
                  <th className="text-right font-medium px-5 py-2.5">Sells</th>
                  <th className="text-right font-medium px-5 py-2.5">Proceeds</th>
                </tr>
              </thead>
              <tbody>
                {realized.map((r) => (
                  <tr key={r.symbol} className="border-b border-slate-700/50 last:border-0">
                    <td className="px-5 py-3 font-semibold text-slate-200">{r.symbol}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{r.txn_count}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(r.proceeds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <p className="text-xs text-slate-500 leading-relaxed">
        Estimates only — not tax advice. The Roth IRA is excluded as a tax-advantaged account.
        {data?.realized_is_partial && ' Realized activity reflects the Schwab orders sync window (~90 days) and shows proceeds without per-lot cost basis, so it understates full-year realized gains/losses.'}
        {' '}Estimated savings apply your selected marginal rate to clean (non-wash-sale) harvestable losses; in practice losses first offset capital gains, then up to {formatCurrency(3000)} of ordinary income per year.
      </p>
    </div>
  )
}
