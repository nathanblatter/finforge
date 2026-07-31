import { useMemo, useState } from 'react'
import Header from '../components/layout/Header'
import { useDividendIncome, useDividendCalendar, useDividendHistory } from '../hooks/useDividends'
import { formatCurrency, formatDate, formatPct } from '../utils/format'
import type { DividendHoldingProjection, DividendCalendarPayment } from '../types'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-slate-100">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

const SOURCE_LABEL: Record<DividendHoldingProjection['source'], string> = {
  market_data: 'Indicated (market data)',
  history: 'Derived from history',
  insufficient_data: 'Not enough history',
}

const SOURCE_COLOR: Record<DividendHoldingProjection['source'], string> = {
  market_data: 'text-sky-400 bg-sky-500/10',
  history: 'text-slate-400 bg-slate-700',
  insufficient_data: 'text-slate-600 bg-slate-800',
}

const CONFIDENCE_COLOR: Record<string, string> = {
  high: 'text-emerald-400 bg-emerald-500/10',
  medium: 'text-amber-400 bg-amber-500/10',
}

export default function DividendsPage() {
  const { data: income, isLoading: incomeLoading } = useDividendIncome()
  const [calendarMonths, setCalendarMonths] = useState(3)
  const { data: calendar, isLoading: calendarLoading } = useDividendCalendar(calendarMonths)
  const [historySymbol, setHistorySymbol] = useState<string | null>(null)
  const { data: history, isLoading: historyLoading } = useDividendHistory(historySymbol ?? undefined)

  const holdings = income?.holdings ?? []

  // Group calendar payments by month for a lightweight calendar list view.
  const calendarByMonth = useMemo(() => {
    const groups = new Map<string, DividendCalendarPayment[]>()
    for (const p of calendar?.payments ?? []) {
      const key = p.expected_pay_date.slice(0, 7)
      const list = groups.get(key) ?? []
      list.push(p)
      groups.set(key, list)
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [calendar])

  return (
    <div className="space-y-6">
      <Header title="Dividends & Income" />

      {incomeLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatTile
              label="Projected annual income"
              value={formatCurrency(income?.portfolio_projected_annual_income ?? 0)}
            />
            <StatTile
              label="Yield on cost"
              value={income?.portfolio_yield_on_cost_pct != null ? formatPct(income.portfolio_yield_on_cost_pct) : '—'}
            />
            <StatTile
              label="Reinvested (DRIP) vs cash"
              value={formatCurrency(income?.portfolio_cumulative_reinvested ?? 0)}
              sub={`${formatCurrency(income?.portfolio_cumulative_cash_received ?? 0)} received as cash`}
            />
          </div>

          {!income?.has_any_market_data_rates && holdings.length > 0 && (
            <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
              No indicated dividend rates available from market data yet — projections below are derived
              purely from payment history (most recent per-share amount × inferred cadence).
            </div>
          )}

          {/* Per-holding projection table */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700 text-sm font-medium text-slate-300">
              Projected income by holding
            </div>
            {holdings.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-8">
                No dividend-paying holdings detected yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b border-slate-700">
                      <th className="px-4 py-2 font-medium">Symbol</th>
                      <th className="px-4 py-2 font-medium text-right">Shares</th>
                      <th className="px-4 py-2 font-medium text-right">Per-share (latest)</th>
                      <th className="px-4 py-2 font-medium">Frequency</th>
                      <th className="px-4 py-2 font-medium text-right">Projected annual</th>
                      <th className="px-4 py-2 font-medium text-right">Yield on cost</th>
                      <th className="px-4 py-2 font-medium">Source</th>
                      <th className="px-4 py-2 font-medium text-right">History</th>
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map((h) => (
                      <tr
                        key={h.symbol}
                        className="border-b border-slate-700/50 last:border-0 hover:bg-slate-700/30 transition-colors"
                      >
                        <td className="px-4 py-2.5 font-medium text-slate-100">{h.symbol}</td>
                        <td className="px-4 py-2.5 text-right text-slate-300">{h.quantity.toLocaleString()}</td>
                        <td className="px-4 py-2.5 text-right text-slate-300">
                          {h.per_share_amount != null ? formatCurrency(h.per_share_amount) : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-slate-400 capitalize">{h.frequency ?? '—'}</td>
                        <td className="px-4 py-2.5 text-right text-slate-100 font-medium">
                          {formatCurrency(h.projected_annual_income)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-300">
                          {h.yield_on_cost_pct != null ? formatPct(h.yield_on_cost_pct) : '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`text-[11px] px-2 py-0.5 rounded-full ${SOURCE_COLOR[h.source]}`}>
                            {SOURCE_LABEL[h.source]}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <button
                            onClick={() => setHistorySymbol(h.symbol === historySymbol ? null : h.symbol)}
                            className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
                          >
                            {historySymbol === h.symbol ? 'Hide' : 'View'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* DRIP / payment history for the selected symbol */}
      {historySymbol && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700 text-sm font-medium text-slate-300">
            {historySymbol} — payment history
          </div>
          {historyLoading ? (
            <Skeleton className="h-32 m-4" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-700">
                    <th className="px-4 py-2 font-medium">Pay date</th>
                    <th className="px-4 py-2 font-medium text-right">Amount</th>
                    <th className="px-4 py-2 font-medium text-right">Per-share</th>
                    <th className="px-4 py-2 font-medium">Type</th>
                    <th className="px-4 py-2 font-medium">Reinvested (DRIP)</th>
                  </tr>
                </thead>
                <tbody>
                  {(history?.transactions ?? []).map((t) => (
                    <tr key={t.id} className="border-b border-slate-700/50 last:border-0">
                      <td className="px-4 py-2.5 text-slate-300">{formatDate(t.pay_date)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-100">{formatCurrency(t.amount)}</td>
                      <td className="px-4 py-2.5 text-right text-slate-400">
                        {t.per_share_amount != null ? formatCurrency(t.per_share_amount) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 capitalize">{t.activity_type}</td>
                      <td className="px-4 py-2.5">
                        {t.is_reinvested ? (
                          <span className="text-[11px] px-2 py-0.5 rounded-full text-emerald-400 bg-emerald-500/10">
                            Reinvested {t.reinvest_amount != null ? formatCurrency(t.reinvest_amount) : ''}
                          </span>
                        ) : (
                          <span className="text-[11px] px-2 py-0.5 rounded-full text-slate-500 bg-slate-700">
                            Cash
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Upcoming ex-div / pay-date calendar */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <span className="text-sm font-medium text-slate-300">Upcoming payment calendar</span>
          <div className="flex gap-1">
            {[3, 6, 12].map((m) => (
              <button
                key={m}
                onClick={() => setCalendarMonths(m)}
                className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${
                  calendarMonths === m
                    ? 'bg-sky-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                {m}mo
              </button>
            ))}
          </div>
        </div>

        {calendarLoading ? (
          <Skeleton className="h-32 m-4" />
        ) : calendarByMonth.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-8">
            Not enough payment history yet to predict upcoming dividends (need at least two prior
            payments per holding).
          </p>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {calendarByMonth.map(([month, payments]) => {
              const monthLabel = new Date(`${month}-01T00:00:00`).toLocaleDateString('en-US', {
                month: 'long',
                year: 'numeric',
              })
              const monthTotal = payments.reduce((sum, p) => sum + p.expected_amount, 0)
              return (
                <div key={month} className="px-4 py-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-slate-200">{monthLabel}</span>
                    <span className="text-sm text-slate-400">{formatCurrency(monthTotal)} expected</span>
                  </div>
                  <div className="space-y-1.5">
                    {payments.map((p, i) => (
                      <div
                        key={`${p.symbol}-${p.expected_pay_date}-${i}`}
                        className="flex items-center justify-between text-sm bg-slate-900/40 rounded-lg px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-100">{p.symbol}</span>
                          <span className="text-xs text-slate-500">{formatDate(p.expected_pay_date)}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${CONFIDENCE_COLOR[p.confidence]}`}>
                            {p.confidence}
                          </span>
                        </div>
                        <span className="text-slate-300">{formatCurrency(p.expected_amount)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
