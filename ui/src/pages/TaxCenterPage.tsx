import { useEffect, useState } from 'react'
import Header from '../components/layout/Header'
import { useToast } from '../components/Toast'
import { useForm1099, useRealizedLots, useTaxEstimates, useTaxSummary } from '../hooks/useTax'
import { api } from '../api/client'
import { formatCurrency, formatDate } from '../utils/format'
import type { RealizedLot, TaxEstimateSettings } from '../types'

const RATE_OPTIONS = [0.12, 0.22, 0.24, 0.30, 0.32, 0.35, 0.37]
const LTCG_OPTIONS = [0.0, 0.15, 0.20, 0.238]
const ESTIMATE_SETTINGS_KEY = 'finforge_tax_estimate_settings'

const DEFAULT_ESTIMATE_SETTINGS: TaxEstimateSettings = {
  prior_year_tax: 0,
  prior_year_agi: 0,
  filing_status: 'single',
  marginal_rate: 0.30,
  ltcg_rate: 0.15,
  set_aside: 0,
}

type Tab = 'overview' | 'lots' | 'estimates' | 'form1099'

const TABS: { label: string; value: Tab }[] = [
  { label: 'Overview', value: 'overview' },
  { label: 'Realized Lots', value: 'lots' },
  { label: 'Estimated Taxes', value: 'estimates' },
  { label: '1099 Reconciliation', value: 'form1099' },
]

function loadEstimateSettings(): TaxEstimateSettings {
  try {
    const raw = localStorage.getItem(ESTIMATE_SETTINGS_KEY)
    if (raw) return { ...DEFAULT_ESTIMATE_SETTINGS, ...JSON.parse(raw) }
  } catch { /* fall through to defaults */ }
  return DEFAULT_ESTIMATE_SETTINGS
}

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

function ExportButton({ label, onExport }: { label: string; onExport: () => Promise<void> }) {
  const [exporting, setExporting] = useState(false)
  const toast = useToast()
  const handle = async () => {
    setExporting(true)
    try {
      await onExport()
      toast.success('CSV downloaded')
    } catch (e: any) {
      toast.error(e?.message ?? 'Export failed')
    } finally {
      setExporting(false)
    }
  }
  return (
    <button
      onClick={handle}
      disabled={exporting}
      className="px-3 py-2 text-sm font-medium bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 rounded-lg transition-colors flex items-center gap-2"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      {exporting ? 'Exporting…' : label}
    </button>
  )
}

function GainCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-500">—</span>
  const cls = value >= 0 ? 'text-emerald-400' : 'text-rose-400'
  return <span className={`tabular-nums ${cls}`}>{value < 0 ? '−' : ''}{formatCurrency(Math.abs(value))}</span>
}

function WashSaleBadge({ details }: { details?: string }) {
  return (
    <span
      title={details ?? 'Replacement purchase within the 30-day wash-sale window'}
      className="ml-2 inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30"
    >
      ⚠ wash sale
    </span>
  )
}

function SourceBanner({ source, coverageStart }: { source: string; coverageStart: string | null }) {
  if (source === 'schwab_transactions') {
    return coverageStart ? (
      <p className="text-xs text-slate-500">
        Lot-level Schwab activity synced from {formatDate(coverageStart)}. Lots acquired earlier show an unknown basis.
      </p>
    ) : null
  }
  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 text-xs text-amber-300">
      Lot-level Schwab activity hasn't synced yet — showing the orders fallback (proceeds only, ~90-day window,
      no cost basis). Figures will fill in after the next nightly Schwab sync.
    </div>
  )
}

// ---------------------------------------------------------------------------
// Overview tab (pre-existing summary content)
// ---------------------------------------------------------------------------

function OverviewTab() {
  const [rate, setRate] = useState(0.30)
  const { data, isLoading } = useTaxSummary(rate)

  const tlh = data?.tlh_opportunities ?? []
  const realized = data?.realized_activity ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        {data?.analysis_date ? (
          <p className="text-xs text-slate-500">
            Taxable brokerage · analysis as of {data.analysis_date} · tax year {data.tax_year}
          </p>
        ) : <span />}
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
          <ExportButton label="Holdings CSV" onExport={() => api.exportTaxHoldings()} />
        </div>
      </div>

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
                      {o.wash_sale_risk && <WashSaleBadge details={o.wash_sale_details ?? undefined} />}
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
            <p className="text-xs text-slate-500 mt-0.5">Sells synced from Schwab orders. See the Realized Lots tab for the per-lot breakdown.</p>
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

      <p className="text-xs text-slate-500 leading-relaxed">
        Estimates only — not tax advice. The Roth IRA is excluded as a tax-advantaged account.
        {data?.realized_is_partial && ' Realized activity reflects the Schwab orders sync window (~90 days) and shows proceeds without per-lot cost basis, so it understates full-year realized gains/losses.'}
        {' '}Estimated savings apply your selected marginal rate to clean (non-wash-sale) harvestable losses; in practice losses first offset capital gains, then up to {formatCurrency(3000)} of ordinary income per year.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Realized Lots tab
// ---------------------------------------------------------------------------

function LotRow({ lot }: { lot: RealizedLot }) {
  return (
    <tr className="border-b border-slate-700/30 last:border-0 text-xs">
      <td className="pl-10 pr-5 py-2 text-slate-400">
        {lot.acquired_date ? formatDate(lot.acquired_date) : <span className="text-amber-400/80" title="Acquired before the synced history window">unknown</span>}
      </td>
      <td className="px-5 py-2 text-slate-400">{formatDate(lot.sold_date)}</td>
      <td className="px-5 py-2 text-right tabular-nums text-slate-400">{lot.quantity ?? '—'}</td>
      <td className="px-5 py-2 text-right tabular-nums text-slate-300">{formatCurrency(lot.proceeds)}</td>
      <td className="px-5 py-2 text-right tabular-nums text-slate-300">{lot.basis !== null ? formatCurrency(lot.basis) : '—'}</td>
      <td className="px-5 py-2 text-right"><GainCell value={lot.gain} /></td>
      <td className="px-5 py-2 text-slate-400 capitalize">
        {lot.term}
        {lot.wash_sale && <WashSaleBadge details={`Disallowed loss ${formatCurrency(lot.disallowed_loss)}`} />}
      </td>
    </tr>
  )
}

function LotsTab() {
  const { data, isLoading } = useRealizedLots()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (symbol: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  const totals = data?.totals
  const symbols = data?.symbols ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <SourceBanner source={data?.source ?? 'none'} coverageStart={data?.coverage_start ?? null} />
        <ExportButton label="Realized CSV (tax prep)" onExport={() => api.exportTaxRealized()} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label={`Net realized · ${data?.tax_year ?? new Date().getFullYear()}`}
          value={formatCurrency(totals?.net_realized ?? 0)}
          tone={(totals?.net_realized ?? 0) >= 0 ? 'gain' : 'loss'}
          sub={`${totals?.lot_count ?? 0} closed lot${(totals?.lot_count ?? 0) === 1 ? '' : 's'} · ${formatCurrency(totals?.proceeds ?? 0)} proceeds`}
        />
        <StatCard
          label="Short-term"
          value={formatCurrency(totals?.net_short_term ?? 0)}
          tone={(totals?.net_short_term ?? 0) >= 0 ? 'gain' : 'loss'}
          sub={`${formatCurrency(totals?.short_term_gain ?? 0)} gains · ${formatCurrency(totals?.short_term_loss ?? 0)} losses`}
        />
        <StatCard
          label="Long-term"
          value={formatCurrency(totals?.net_long_term ?? 0)}
          tone={(totals?.net_long_term ?? 0) >= 0 ? 'gain' : 'loss'}
          sub={`${formatCurrency(totals?.long_term_gain ?? 0)} gains · ${formatCurrency(totals?.long_term_loss ?? 0)} losses`}
        />
      </div>

      {(totals?.wash_sale_disallowed ?? 0) > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3 text-xs text-amber-300">
          {formatCurrency(totals!.wash_sale_disallowed)} of realized losses are flagged as wash-sale disallowed
          (replacement purchase within 30 days). These can't be deducted this year.
        </div>
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-200">Per-lot breakdown</h2>
          <p className="text-xs text-slate-500 mt-0.5">FIFO-matched closed lots. Click a symbol to expand its lots.</p>
        </div>
        {symbols.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-400">No realized lots this year.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-slate-700">
                  <th className="text-left font-medium px-5 py-2.5">Symbol</th>
                  <th className="text-right font-medium px-5 py-2.5">Lots</th>
                  <th className="text-right font-medium px-5 py-2.5">Proceeds</th>
                  <th className="text-right font-medium px-5 py-2.5">Basis</th>
                  <th className="text-right font-medium px-5 py-2.5">Gain</th>
                  <th className="text-right font-medium px-5 py-2.5">ST / LT</th>
                </tr>
              </thead>
              <tbody>
                {symbols.map((g) => (
                  <>
                    <tr
                      key={g.symbol}
                      onClick={() => toggle(g.symbol)}
                      className="border-b border-slate-700/50 last:border-0 cursor-pointer hover:bg-slate-700/20"
                    >
                      <td className="px-5 py-3">
                        <span className="text-slate-500 mr-2 text-xs">{expanded.has(g.symbol) ? '▾' : '▸'}</span>
                        <span className="font-semibold text-slate-200">{g.symbol}</span>
                        {g.wash_sale_disallowed > 0 && <WashSaleBadge details={`Disallowed ${formatCurrency(g.wash_sale_disallowed)}`} />}
                        {g.has_unknown_basis && (
                          <span className="ml-2 text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-600/40 text-slate-400 border border-slate-600" title="Some lots were acquired before the synced history window">
                            partial basis
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-slate-300">{g.lot_count}</td>
                      <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(g.proceeds)}</td>
                      <td className="px-5 py-3 text-right tabular-nums text-slate-300">{g.basis !== null ? formatCurrency(g.basis) : '—'}</td>
                      <td className="px-5 py-3 text-right"><GainCell value={g.gain} /></td>
                      <td className="px-5 py-3 text-right text-xs tabular-nums text-slate-400">
                        <GainCell value={g.net_short_term} /> / <GainCell value={g.net_long_term} />
                      </td>
                    </tr>
                    {expanded.has(g.symbol) && (
                      <tr key={`${g.symbol}-lots`} className="bg-slate-900/40">
                        <td colSpan={6} className="p-0">
                          <table className="w-full">
                            <thead>
                              <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                                <th className="text-left font-medium pl-10 pr-5 py-2">Acquired</th>
                                <th className="text-left font-medium px-5 py-2">Sold</th>
                                <th className="text-right font-medium px-5 py-2">Qty</th>
                                <th className="text-right font-medium px-5 py-2">Proceeds</th>
                                <th className="text-right font-medium px-5 py-2">Basis</th>
                                <th className="text-right font-medium px-5 py-2">Gain</th>
                                <th className="text-left font-medium px-5 py-2">Term</th>
                              </tr>
                            </thead>
                            <tbody>
                              {g.lots.map((lot, i) => <LotRow key={i} lot={lot} />)}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(totals?.unknown_basis_lots ?? 0) > 0 && (
        <p className="text-xs text-slate-500">
          {totals!.unknown_basis_lots} lot{totals!.unknown_basis_lots === 1 ? '' : 's'} ({formatCurrency(totals!.unknown_basis_proceeds)} proceeds)
          were acquired before the synced Schwab history and show no basis — check the broker's records for those.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Estimated Taxes tab
// ---------------------------------------------------------------------------

function SettingsField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-400">
      {label}
      {children}
    </label>
  )
}

const inputClass = 'bg-slate-900 border border-slate-600 rounded-lg px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500 w-full'

function EstimatesTab() {
  const [settings, setSettings] = useState<TaxEstimateSettings>(loadEstimateSettings)
  const { data, isLoading } = useTaxEstimates(settings)

  useEffect(() => {
    localStorage.setItem(ESTIMATE_SETTINGS_KEY, JSON.stringify(settings))
  }, [settings])

  const update = (patch: Partial<TaxEstimateSettings>) =>
    setSettings((prev) => ({ ...prev, ...patch }))

  const numberInput = (key: 'prior_year_tax' | 'prior_year_agi' | 'set_aside') => (
    <input
      type="number"
      min={0}
      step={100}
      value={settings[key] || ''}
      placeholder="0"
      onChange={(e) => update({ [key]: Number(e.target.value) || 0 })}
      className={inputClass}
    />
  )

  const q = data?.quarters ?? []

  return (
    <div className="space-y-6">
      {/* Settings */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-1">Estimate settings</h2>
        <p className="text-xs text-slate-500 mb-4">Saved locally in this browser. Safe harbor uses 110% of prior-year tax when prior AGI exceeds $150k ($75k married filing separately).</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <SettingsField label="Prior-year tax">{numberInput('prior_year_tax')}</SettingsField>
          <SettingsField label="Prior-year AGI">{numberInput('prior_year_agi')}</SettingsField>
          <SettingsField label="Filing status">
            <select
              value={settings.filing_status}
              onChange={(e) => update({ filing_status: e.target.value as TaxEstimateSettings['filing_status'] })}
              className={inputClass}
            >
              <option value="single">Single</option>
              <option value="married_joint">Married joint</option>
              <option value="married_separate">Married separate</option>
              <option value="head_of_household">Head of household</option>
            </select>
          </SettingsField>
          <SettingsField label="Marginal rate">
            <select value={settings.marginal_rate} onChange={(e) => update({ marginal_rate: Number(e.target.value) })} className={inputClass}>
              {RATE_OPTIONS.map((r) => <option key={r} value={r}>{(r * 100).toFixed(0)}%</option>)}
            </select>
          </SettingsField>
          <SettingsField label="LTCG rate">
            <select value={settings.ltcg_rate} onChange={(e) => update({ ltcg_rate: Number(e.target.value) })} className={inputClass}>
              {LTCG_OPTIONS.map((r) => <option key={r} value={r}>{(r * 100).toFixed(1)}%</option>)}
            </select>
          </SettingsField>
          <SettingsField label="Set aside so far">{numberInput('set_aside')}</SettingsField>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
          <Skeleton className="h-48" />
        </div>
      ) : data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard
              label="Est. tax on YTD investment income"
              value={formatCurrency(data.est_total_tax)}
              tone="neutral"
              sub={`ST ${formatCurrency(data.est_tax_short_term)} · LT ${formatCurrency(data.est_tax_long_term)} · div ${formatCurrency(data.est_tax_dividends)} · int ${formatCurrency(data.est_tax_interest)}`}
            />
            <StatCard
              label="Safe-harbor target (annual)"
              value={formatCurrency(data.required_annual)}
              tone="accent"
              sub={data.prior_year_tax > 0
                ? `min of ${(data.safe_harbor_pct * 100).toFixed(0)}% prior-year (${formatCurrency(data.safe_harbor_prior_year)}) and 90% current (${formatCurrency(data.safe_harbor_current_year)})`
                : '90% of current-year estimate'}
            />
            <StatCard
              label="Still to set aside"
              value={formatCurrency(data.remaining)}
              tone={data.remaining > 0 ? 'loss' : 'gain'}
              sub={`${formatCurrency(data.set_aside)} already set aside`}
            />
          </div>

          {/* YTD income picture */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700">
              <h2 className="text-sm font-semibold text-slate-200">YTD investment income · {data.tax_year}</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 divide-x divide-slate-700/50 text-center">
              {[
                ['Net short-term', data.ytd_net_short_term],
                ['Net long-term', data.ytd_net_long_term],
                ['Ordinary dividends', data.ytd_ordinary_dividends],
                ['Qualified dividends', data.ytd_qualified_dividends],
                ['Interest', data.ytd_interest],
              ].map(([label, value]) => (
                <div key={label as string} className="px-4 py-4">
                  <div className="text-xs text-slate-500 mb-1">{label}</div>
                  <div className="text-sm font-semibold tabular-nums"><GainCell value={value as number} /></div>
                </div>
              ))}
            </div>
          </div>

          {/* Quarterly schedule */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700">
              <h2 className="text-sm font-semibold text-slate-200">IRS quarterly schedule · {data.tax_year}</h2>
              <p className="text-xs text-slate-500 mt-0.5">Cumulative safe-harbor targets vs. what you've set aside ({formatCurrency(data.set_aside)}).</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 border-b border-slate-700">
                    <th className="text-left font-medium px-5 py-2.5">Quarter</th>
                    <th className="text-left font-medium px-5 py-2.5">Income period</th>
                    <th className="text-left font-medium px-5 py-2.5">Due date</th>
                    <th className="text-right font-medium px-5 py-2.5">Quarter payment</th>
                    <th className="text-right font-medium px-5 py-2.5">Cumulative target</th>
                    <th className="text-right font-medium px-5 py-2.5">Covered?</th>
                  </tr>
                </thead>
                <tbody>
                  {q.map((quarter) => {
                    // API Decimals serialize as strings — coerce before comparing.
                    const covered = Number(data.set_aside) >= Number(quarter.required_cumulative)
                    return (
                      <tr key={quarter.quarter} className={`border-b border-slate-700/50 last:border-0 ${quarter.status === 'due_next' ? 'bg-sky-500/5' : ''}`}>
                        <td className="px-5 py-3 font-semibold text-slate-200">
                          {quarter.quarter}
                          {quarter.status === 'due_next' && (
                            <span className="ml-2 text-[10px] font-medium px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-400 border border-sky-500/30">next due</span>
                          )}
                        </td>
                        <td className="px-5 py-3 text-slate-400 text-xs">{quarter.period}</td>
                        <td className={`px-5 py-3 tabular-nums ${quarter.status === 'past' ? 'text-slate-500' : 'text-slate-300'}`}>{formatDate(quarter.due_date)}</td>
                        <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(quarter.required_quarter)}</td>
                        <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(quarter.required_cumulative)}</td>
                        <td className="px-5 py-3 text-right">
                          {covered
                            ? <span className="text-emerald-400 text-xs font-medium">✓ covered</span>
                            : <span className="text-rose-400 text-xs font-medium tabular-nums">short {formatCurrency(quarter.required_cumulative - data.set_aside)}</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {data.notes.length > 0 && (
            <ul className="text-xs text-slate-500 leading-relaxed list-disc pl-4 space-y-1">
              {data.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 1099 Reconciliation tab
// ---------------------------------------------------------------------------

function Form1099Tab() {
  const { data, isLoading } = useForm1099()

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  const symbols = data?.symbols ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <SourceBanner source={data?.source ?? 'none'} coverageStart={data?.coverage_start ?? null} />
        <ExportButton label="1099 CSV" onExport={() => api.exportForm1099()} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="1099-B · proceeds / basis"
          value={formatCurrency(data?.total_proceeds ?? 0)}
          sub={`basis ${formatCurrency(data?.total_basis ?? 0)} · wash-sale disallowed ${formatCurrency(data?.total_wash_sale_disallowed ?? 0)}`}
        />
        <StatCard
          label="1099-B · gains (ST / LT)"
          value={`${formatCurrency(data?.short_term_gain ?? 0)} / ${formatCurrency(data?.long_term_gain ?? 0)}`}
          sub={`ST proceeds ${formatCurrency(data?.short_term_proceeds ?? 0)} · LT proceeds ${formatCurrency(data?.long_term_proceeds ?? 0)}`}
        />
        <StatCard
          label="1099-DIV / 1099-INT"
          value={formatCurrency(Number(data?.total_ordinary_dividends ?? 0) + Number(data?.total_qualified_dividends ?? 0))}
          sub={`qualified ${formatCurrency(data?.total_qualified_dividends ?? 0)} · interest ${formatCurrency(data?.total_interest ?? 0)}`}
        />
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-200">Per-symbol reconciliation · {data?.tax_year ?? new Date().getFullYear()}</h2>
          <p className="text-xs text-slate-500 mt-0.5">Compare these rows against the broker's 1099 — the broker form is authoritative.</p>
        </div>
        {symbols.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-400">No reportable activity this year.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-slate-700">
                  <th className="text-left font-medium px-5 py-2.5">Symbol</th>
                  <th className="text-right font-medium px-5 py-2.5">Proceeds</th>
                  <th className="text-right font-medium px-5 py-2.5">Basis</th>
                  <th className="text-right font-medium px-5 py-2.5">Wash disallowed</th>
                  <th className="text-right font-medium px-5 py-2.5">Gain</th>
                  <th className="text-right font-medium px-5 py-2.5">Ordinary div</th>
                  <th className="text-right font-medium px-5 py-2.5">Qualified div</th>
                </tr>
              </thead>
              <tbody>
                {symbols.map((r) => (
                  <tr key={r.symbol} className="border-b border-slate-700/50 last:border-0">
                    <td className="px-5 py-3">
                      <span className="font-semibold text-slate-200">{r.symbol}</span>
                      {r.has_unknown_basis && (
                        <span className="ml-2 text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-600/40 text-slate-400 border border-slate-600" title="Some lots have unknown basis">
                          partial basis
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{formatCurrency(r.proceeds)}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{r.basis !== null ? formatCurrency(r.basis) : '—'}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-amber-400">{r.wash_sale_disallowed > 0 ? formatCurrency(r.wash_sale_disallowed) : '—'}</td>
                    <td className="px-5 py-3 text-right"><GainCell value={r.gain} /></td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{r.ordinary_dividends > 0 ? formatCurrency(r.ordinary_dividends) : '—'}</td>
                    <td className="px-5 py-3 text-right tabular-nums text-slate-300">{r.qualified_dividends > 0 ? formatCurrency(r.qualified_dividends) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(data?.notes.length ?? 0) > 0 && (
        <ul className="text-xs text-slate-500 leading-relaxed list-disc pl-4 space-y-1">
          {data!.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TaxCenterPage() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div className="space-y-6 max-w-[1100px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Tax Center" />
        <div className="flex gap-1 bg-slate-800 border border-slate-700 rounded-lg p-1">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={[
                'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                tab === t.value ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-200',
              ].join(' ')}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'lots' && <LotsTab />}
      {tab === 'estimates' && <EstimatesTab />}
      {tab === 'form1099' && <Form1099Tab />}
    </div>
  )
}
