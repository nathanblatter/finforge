import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { formatCurrency } from '../../utils/format'

function Stat({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-4">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-lg font-bold ${accent ? 'text-sky-400' : 'text-slate-100'}`}>{value}</div>
    </div>
  )
}

export default function WrappedCard() {
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(new Date().getMonth() <= 1 ? currentYear - 1 : currentYear)
  const qc = useQueryClient()

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['wrapped', year],
    queryFn: () => api.getWrapped(year),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const regenerate = async () => {
    await qc.fetchQuery({
      queryKey: ['wrapped', year],
      queryFn: () => api.getWrapped(year, true),
    })
  }

  const years = []
  for (let y = currentYear; y >= currentYear - 4; y--) years.push(y)

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-slate-800 to-slate-800/60 border border-sky-500/20 rounded-xl p-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-1">
          <h3 className="text-lg font-bold text-slate-100">
            🎁 FinForge Wrapped {year}
            {data?.partial_year && <span className="text-xs font-normal text-amber-400 ml-2">(year in progress)</span>}
          </h3>
          <div className="flex items-center gap-2">
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
            >
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <button
              onClick={regenerate}
              disabled={isFetching}
              className="px-3 py-1.5 text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors disabled:opacity-50"
            >
              {isFetching ? 'Working...' : 'Regenerate'}
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="bg-slate-700 animate-pulse rounded-xl h-40 mt-4" />
        ) : error ? (
          <p className="text-sm text-slate-500 py-8 text-center">No data for {year} yet.</p>
        ) : data?.narrative ? (
          <p className="text-sm text-slate-300 leading-relaxed mt-3 whitespace-pre-line">{data.narrative}</p>
        ) : (
          <p className="text-sm text-slate-500 mt-3">Narrative unavailable — stats below.</p>
        )}
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat label="Total Spend" value={formatCurrency(data.stats.total_spend)} />
            <Stat label="Transactions" value={data.stats.transaction_count.toLocaleString()} />
            <Stat
              label="Net Worth Change"
              value={`${data.stats.net_worth_change >= 0 ? '+' : ''}${formatCurrency(data.stats.net_worth_change)}`}
              accent
            />
            <Stat
              label="Biggest Month"
              value={data.stats.biggest_month ? `${data.stats.biggest_month[0]} · ${formatCurrency(data.stats.biggest_month[1])}` : '—'}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-3">Top Merchants ($)</h4>
              <div className="space-y-1.5">
                {data.stats.top_merchants_by_total.map(([m, v]) => (
                  <div key={m} className="flex items-center justify-between text-sm">
                    <Link
                      to={`/merchant?name=${encodeURIComponent(m)}`}
                      className="text-slate-300 truncate pr-3 hover:text-sky-400 transition-colors"
                    >
                      {m}
                    </Link>
                    <span className="text-slate-400 tabular-nums shrink-0">{formatCurrency(v)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-3">Most Visited</h4>
              <div className="space-y-1.5">
                {data.stats.top_merchants_by_visits.map(([m, n]) => (
                  <div key={m} className="flex items-center justify-between text-sm">
                    <Link
                      to={`/merchant?name=${encodeURIComponent(m)}`}
                      className="text-slate-300 truncate pr-3 hover:text-sky-400 transition-colors"
                    >
                      {m}
                    </Link>
                    <span className="text-slate-400 tabular-nums shrink-0">{n}×</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-3">Portfolio</h4>
              <div className="space-y-2 text-sm">
                {data.stats.best_holding && (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Best holding</span>
                    <span className="text-emerald-400">{data.stats.best_holding[0]} +{data.stats.best_holding[1]}%</span>
                  </div>
                )}
                {data.stats.worst_holding && (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Roughest holding</span>
                    <span className="text-rose-400">{data.stats.worst_holding[0]} {data.stats.worst_holding[1]}%</span>
                  </div>
                )}
                {data.stats.largest_purchase && (
                  <div className="pt-2 border-t border-slate-700">
                    <div className="text-slate-400 text-xs mb-1">Largest single purchase</div>
                    <div className="text-slate-200">
                      {data.stats.largest_purchase[0]} — {formatCurrency(data.stats.largest_purchase[1])}
                      <span className="text-slate-500 text-xs ml-2">{data.stats.largest_purchase[2]}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
