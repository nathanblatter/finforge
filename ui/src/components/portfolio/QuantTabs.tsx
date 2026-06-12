import { useState } from 'react'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ComposedChart, Area, Line, ResponsiveContainer, Legend,
} from 'recharts'
import { useFrontier, useClusters, useIvHv, useMonteCarlo } from '../../hooks/useQuant'
import { formatCurrency, formatPct } from '../../utils/format'
import type { MonteCarloResponse } from '../../types'

function Panel({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-1">{title}</h3>
      {sub && <p className="text-xs text-slate-500 mb-4">{sub}</p>}
      {children}
    </div>
  )
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function WeightsList({ weights }: { weights: Record<string, number> }) {
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-1">
      {entries.map(([sym, w]) => (
        <div key={sym} className="flex items-center justify-between text-xs">
          <span className="text-slate-300">{sym}</span>
          <span className="text-slate-400 tabular-nums">{(w * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Efficient Frontier + Clusters
// ---------------------------------------------------------------------------

export function FrontierTab() {
  const { data, isLoading, error } = useFrontier()
  const { data: clusters, isLoading: clustersLoading } = useClusters()

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-80" /><Skeleton className="h-40" /></div>
  if (error || !data) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
        <p className="text-slate-400 text-sm">Couldn't compute the frontier.</p>
        <p className="text-slate-500 text-xs mt-1">Needs at least 2 non-cash holdings and a valid Schwab connection.</p>
      </div>
    )
  }

  const cloudPts = data.cloud.map((p) => ({ ...p, vol: p.vol * 100, ret: p.ret * 100 }))
  const special = [
    { name: 'Max Sharpe', vol: data.max_sharpe.vol * 100, ret: data.max_sharpe.ret * 100, fill: '#34d399' },
    { name: 'Min Variance', vol: data.min_variance.vol * 100, ret: data.min_variance.ret * 100, fill: '#38bdf8' },
    ...(data.current ? [{ name: 'Your Portfolio', vol: data.current.vol * 100, ret: data.current.ret * 100, fill: '#f59e0b' }] : []),
  ]

  return (
    <div className="space-y-6">
      <Panel
        title="Efficient Frontier"
        sub={`${data.cloud.length.toLocaleString()} simulated long-only portfolios over your ${data.symbols.length} holdings (${data.lookback_days} trading days of history). Risk-free rate ${(data.risk_free_rate * 100).toFixed(1)}%.`}
      >
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
              <XAxis
                type="number" dataKey="vol" name="Volatility" unit="%"
                stroke="#64748b" fontSize={11} domain={['auto', 'auto']}
                label={{ value: 'Annualized Volatility (%)', position: 'insideBottom', offset: -5, fill: '#64748b', fontSize: 11 }}
              />
              <YAxis
                type="number" dataKey="ret" name="Return" unit="%"
                stroke="#64748b" fontSize={11} domain={['auto', 'auto']}
              />
              <ZAxis range={[12, 12]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                formatter={(v: number) => `${v.toFixed(1)}%`}
              />
              <Scatter name="Portfolios" data={cloudPts} fill="#475569" opacity={0.5} />
              {special.map((s) => (
                <Scatter key={s.name} name={s.name} data={[s]} fill={s.fill} shape="diamond"
                  // @ts-ignore recharts typing for per-scatter ZAxis
                  zAxisId={undefined} r={8} />
              ))}
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Panel title="Max Sharpe Portfolio" sub={`Sharpe ${data.max_sharpe.sharpe.toFixed(2)} — ${(data.max_sharpe.ret * 100).toFixed(1)}% return / ${(data.max_sharpe.vol * 100).toFixed(1)}% vol`}>
          <WeightsList weights={data.max_sharpe.weights} />
        </Panel>
        <Panel title="Min Variance Portfolio" sub={`Sharpe ${data.min_variance.sharpe.toFixed(2)} — ${(data.min_variance.ret * 100).toFixed(1)}% return / ${(data.min_variance.vol * 100).toFixed(1)}% vol`}>
          <WeightsList weights={data.min_variance.weights} />
        </Panel>
        <Panel
          title="Your Portfolio"
          sub={data.current ? `Sharpe ${data.current.sharpe.toFixed(2)} — ${(data.current.ret * 100).toFixed(1)}% return / ${(data.current.vol * 100).toFixed(1)}% vol` : 'No current weights'}
        >
          <div className="space-y-1">
            {data.per_symbol
              .filter((s) => s.current_weight > 0)
              .sort((a, b) => b.current_weight - a.current_weight)
              .map((s) => (
                <div key={s.symbol} className="flex items-center justify-between text-xs">
                  <span className="text-slate-300">{s.symbol}</span>
                  <span className="text-slate-400 tabular-nums">{(s.current_weight * 100).toFixed(1)}%</span>
                </div>
              ))}
          </div>
        </Panel>
      </div>

      <Panel
        title="Correlation Clusters"
        sub={clusters ? `Holdings whose returns correlate above ${clusters.corr_threshold} are grouped — you hold ${clusters.n_positions} positions but only ${clusters.n_clusters} truly independent bet${clusters.n_clusters === 1 ? '' : 's'}.` : undefined}
      >
        {clustersLoading ? (
          <Skeleton className="h-24" />
        ) : !clusters ? (
          <p className="text-sm text-slate-500">Cluster analysis unavailable.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {clusters.clusters.map((c, i) => (
              <div key={i} className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-slate-400">Cluster {i + 1}</span>
                  <span className="text-xs text-slate-500">{c.weight_pct.toFixed(1)}% of portfolio</span>
                </div>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {c.symbols.map((s) => (
                    <span key={s} className="text-xs font-medium px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20">{s}</span>
                  ))}
                </div>
                {c.symbols.length > 1 && (
                  <div className="text-[11px] text-slate-500">avg internal correlation {c.avg_internal_correlation.toFixed(2)}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

// ---------------------------------------------------------------------------
// IV vs HV
// ---------------------------------------------------------------------------

const SIGNAL_STYLES: Record<string, string> = {
  RICH: 'bg-amber-500/15 text-amber-400',
  CHEAP: 'bg-emerald-500/15 text-emerald-400',
  FAIR: 'bg-slate-700 text-slate-400',
  UNKNOWN: 'bg-slate-700 text-slate-500',
}

export function VolatilityTab() {
  const { data, isLoading, error } = useIvHv()

  if (isLoading) return <Skeleton className="h-64" />
  if (error || !data) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
        <p className="text-slate-400 text-sm">Couldn't load volatility data.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Panel
        title="Implied vs Historical Volatility"
        sub="~30-day ATM implied vol from the options chain vs realized 30-day volatility. RICH = options expensive (favors selling covered calls); CHEAP = protection is cheap."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-4">Symbol</th>
                <th className="pb-2 pr-4 text-right">HV (30d)</th>
                <th className="pb-2 pr-4 text-right">IV (~30d)</th>
                <th className="pb-2 pr-4 text-right">IV / HV</th>
                <th className="pb-2 text-center">Signal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {data.results.map((r) => (
                <tr key={r.symbol} className="hover:bg-slate-700/30 transition-colors">
                  <td className="py-2.5 pr-4 font-medium text-slate-100">{r.symbol}</td>
                  <td className="py-2.5 pr-4 text-right text-slate-300">
                    {r.hv_30d != null ? formatPct(r.hv_30d * 100) : '—'}
                  </td>
                  <td className="py-2.5 pr-4 text-right text-slate-300">
                    {r.iv_30d != null ? formatPct(r.iv_30d * 100) : '—'}
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">
                    {r.iv_hv_ratio != null ? (
                      <span className={r.iv_hv_ratio > 1.25 ? 'text-amber-400' : r.iv_hv_ratio < 0.8 ? 'text-emerald-400' : 'text-slate-400'}>
                        {r.iv_hv_ratio.toFixed(2)}×
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2.5 text-center">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${SIGNAL_STYLES[r.signal]}`}>
                      {r.signal}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.results.every((r) => r.iv_30d == null) && (
          <p className="text-xs text-slate-500 mt-3">
            No options data available — symbols without listed options (e.g. mutual funds) show HV only.
          </p>
        )}
      </Panel>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Monte Carlo projections
// ---------------------------------------------------------------------------

export function ProjectionsTab() {
  const monteCarlo = useMonteCarlo()
  const [contribution, setContribution] = useState('500')
  const [years, setYears] = useState('10')
  const [target, setTarget] = useState('')
  const [result, setResult] = useState<MonteCarloResponse | null>(null)

  const run = () => {
    monteCarlo.mutate(
      {
        monthly_contribution: parseFloat(contribution) || 0,
        years: Math.max(1, Math.min(50, parseInt(years) || 10)),
        target_value: target ? parseFloat(target) : undefined,
      },
      { onSuccess: setResult },
    )
  }

  const chartData = result?.yearly.map((y) => ({
    year: `Y${y.year}`,
    band80: [y.p10, y.p90],
    band50: [y.p25, y.p75],
    median: y.p50,
  }))

  return (
    <div className="space-y-6">
      <Panel
        title="Monte Carlo Projection"
        sub="Block-bootstrap simulation using your portfolio's own return history — fat tails included, no normal-distribution assumption."
      >
        <div className="flex flex-wrap items-end gap-4 mb-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Monthly contribution ($)</label>
            <input
              type="number" min="0" step="50" value={contribution}
              onChange={(e) => setContribution(e.target.value)}
              className="w-32 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Years</label>
            <input
              type="number" min="1" max="50" value={years}
              onChange={(e) => setYears(e.target.value)}
              className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Target value ($, optional)</label>
            <input
              type="number" min="0" step="1000" value={target} placeholder="e.g. 100000"
              onChange={(e) => setTarget(e.target.value)}
              className="w-36 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500"
            />
          </div>
          <button
            onClick={run}
            disabled={monteCarlo.isPending}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {monteCarlo.isPending ? 'Simulating...' : 'Run Simulation'}
          </button>
        </div>

        {result && chartData && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider">Starting Value</div>
                <div className="text-lg font-bold text-slate-100">{formatCurrency(result.initial_value)}</div>
              </div>
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider">Median at Year {result.years}</div>
                <div className="text-lg font-bold text-emerald-400">{result.final_median != null ? formatCurrency(result.final_median) : '—'}</div>
              </div>
              {result.prob_hit_at_horizon != null && (
                <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider">Hits {formatCurrency(result.target_value!)} by Y{result.years}</div>
                  <div className="text-lg font-bold text-sky-400">{(result.prob_hit_at_horizon * 100).toFixed(0)}%</div>
                </div>
              )}
              {result.prob_hit_ever != null && (
                <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider">Hits Target at Any Point</div>
                  <div className="text-lg font-bold text-sky-400">{(result.prob_hit_ever * 100).toFixed(0)}%</div>
                </div>
              )}
            </div>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 0, left: 10 }}>
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                  <XAxis dataKey="year" stroke="#64748b" fontSize={11} />
                  <YAxis
                    stroke="#64748b" fontSize={11}
                    tickFormatter={(v: number) => v >= 1000000 ? `$${(v / 1000000).toFixed(1)}M` : `$${(v / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number | number[]) =>
                      Array.isArray(v) ? `${formatCurrency(v[0])} – ${formatCurrency(v[1])}` : formatCurrency(v)
                    }
                  />
                  <Area dataKey="band80" name="10th–90th pct" stroke="none" fill="#0ea5e9" fillOpacity={0.12} />
                  <Area dataKey="band50" name="25th–75th pct" stroke="none" fill="#0ea5e9" fillOpacity={0.25} />
                  <Line dataKey="median" name="Median" stroke="#38bdf8" strokeWidth={2} dot={false} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="text-xs text-slate-500 mt-3">
              {result.n_sims.toLocaleString()} simulations. Bands show the spread of outcomes; this is a projection from
              one year of return history, not a guarantee.
            </p>
          </>
        )}
      </Panel>
    </div>
  )
}
