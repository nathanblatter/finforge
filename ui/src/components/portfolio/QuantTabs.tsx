import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  ComposedChart, Area, Line, ResponsiveContainer, Legend,
} from 'recharts'
import { useFrontier, useClusters, useIvHv, useMonteCarlo } from '../../hooks/useQuant'
import { formatCurrency, formatPct } from '../../utils/format'
import type { FrontierResponse, MonteCarloResponse, WhatIfResponse } from '../../types'

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
  const [whatIf, setWhatIf] = useState<WhatIfResponse | null>(null)

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
    ...(whatIf ? [{ name: 'What-If', vol: whatIf.whatif.vol * 100, ret: whatIf.whatif.ret * 100, fill: '#e879f9' }] : []),
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

      <WhatIfPanel data={data} onResult={setWhatIf} />

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
// What-if rebalancer
// ---------------------------------------------------------------------------

function WhatIfDelta({ label, now, was, pct = false }: { label: string; now: number; was: number | null; pct?: boolean }) {
  const fmt = (v: number) => pct ? `${(v * 100).toFixed(1)}%` : v.toFixed(2)
  const delta = was != null ? now - was : null
  return (
    <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className="text-lg font-bold text-fuchsia-300">{fmt(now)}</div>
      {delta != null && Math.abs(delta) > 1e-6 && (
        <div className={`text-[11px] ${delta > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          {delta > 0 ? '+' : ''}{fmt(delta)} vs current
        </div>
      )}
    </div>
  )
}

function WhatIfPanel({ data, onResult }: { data: FrontierResponse; onResult: (r: WhatIfResponse | null) => void }) {
  const initial = useMemo(
    () => Object.fromEntries(data.per_symbol.map((s) => [s.symbol, Math.round(s.current_weight * 1000) / 10])),
    [data.per_symbol],
  )
  const [weights, setWeights] = useState<Record<string, number>>(initial)
  const [touched, setTouched] = useState(false)
  const [result, setResult] = useState<WhatIfResponse | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  const mutation = useMutation({
    mutationFn: api.runWhatIf,
    onSuccess: (r) => {
      setResult(r)
      onResult(r)
    },
  })
  const { mutate } = mutation

  useEffect(() => {
    if (!touched) return
    clearTimeout(timer.current)
    timer.current = setTimeout(() => mutate(weights), 400)
    return () => clearTimeout(timer.current)
  }, [weights, touched, mutate])

  const total = Object.values(weights).reduce((s, v) => s + v, 0)

  const reset = () => {
    setWeights(initial)
    setTouched(false)
    setResult(null)
    onResult(null)
  }

  return (
    <Panel
      title="What-If Rebalancer"
      sub="Drag the sliders to a hypothetical allocation — the magenta diamond on the chart above shows where it lands. Weights are normalized to 100%."
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-3 mb-4">
        {data.per_symbol.map((s) => {
          const w = weights[s.symbol] ?? 0
          const normPct = total > 0 ? (w / total) * 100 : 0
          return (
            <div key={s.symbol} className="flex items-center gap-3">
              <span className="w-14 text-xs font-medium text-slate-300">{s.symbol}</span>
              <input
                type="range" min="0" max="100" step="0.5" value={w}
                onChange={(e) => {
                  setTouched(true)
                  setWeights((prev) => ({ ...prev, [s.symbol]: Number(e.target.value) }))
                }}
                className="flex-1 accent-fuchsia-400"
              />
              <span className="w-12 text-right text-xs text-slate-400 tabular-nums">{normPct.toFixed(1)}%</span>
            </div>
          )
        })}
      </div>

      <div className="flex items-start justify-between flex-wrap gap-4">
        {result ? (
          <div className="grid grid-cols-3 gap-3 flex-1 min-w-[280px]">
            <WhatIfDelta label="Exp. Return" now={result.whatif.ret} was={result.current?.ret ?? null} pct />
            <WhatIfDelta label="Volatility" now={result.whatif.vol} was={result.current?.vol ?? null} pct />
            <WhatIfDelta label="Sharpe" now={result.whatif.sharpe} was={result.current?.sharpe ?? null} />
          </div>
        ) : (
          <p className="text-xs text-slate-500 self-center">
            {mutation.isPending ? 'Computing…' : touched ? '' : 'Sliders start at your current allocation.'}
          </p>
        )}
        <button
          onClick={reset}
          disabled={!touched}
          className="px-3 py-1.5 text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors disabled:opacity-40"
        >
          Reset to current
        </button>
      </div>
      {mutation.isError && (
        <p className="text-xs text-rose-400 mt-2">Couldn't compute — try again in a moment.</p>
      )}
    </Panel>
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

      <CoveredCallsPanel />
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

// ---------------------------------------------------------------------------
// Covered calls
// ---------------------------------------------------------------------------

function useCoveredCalls() {
  return useQuery({
    queryKey: ['quant', 'covered-calls'],
    queryFn: api.getCoveredCalls,
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

export function CoveredCallsPanel() {
  const { data, isLoading } = useCoveredCalls()

  if (isLoading) return <Skeleton className="h-48" />
  if (!data) return null
  const sellable = data.results.filter((r) => r.call && r.contracts_available > 0)
  const totalAnnual = sellable.reduce((s, r) => s + (r.est_annual_income ?? 0), 0)

  return (
    <Panel
      title="Covered Call Income"
      sub={`~30-delta calls, 20–45 days out, on positions where you own ≥100 shares. Premiums are mid-market — actual fills vary.${sellable.length > 0 ? ` Estimated total: ${formatCurrency(totalAnnual)}/yr if rolled continuously.` : ''}`}
    >
      {data.results.length === 0 ? (
        <p className="text-sm text-slate-500">No holdings to screen.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-4">Symbol</th>
                <th className="pb-2 pr-4 text-right">Shares</th>
                <th className="pb-2 pr-4 text-right">Strike</th>
                <th className="pb-2 pr-4 text-right">DTE</th>
                <th className="pb-2 pr-4 text-right">Delta</th>
                <th className="pb-2 pr-4 text-right">Premium</th>
                <th className="pb-2 pr-4 text-right">Ann. Yield</th>
                <th className="pb-2 text-right">Est. Income/yr</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {data.results.map((r) => (
                <tr key={r.symbol} className="hover:bg-slate-700/30 transition-colors">
                  <td className="py-2.5 pr-4 font-medium text-slate-100">{r.symbol}</td>
                  <td className="py-2.5 pr-4 text-right text-slate-400 tabular-nums">{r.shares.toFixed(0)}</td>
                  {r.call ? (
                    <>
                      <td className="py-2.5 pr-4 text-right text-slate-300">${r.call.strike}</td>
                      <td className="py-2.5 pr-4 text-right text-slate-400">{r.call.expiration_days}d</td>
                      <td className="py-2.5 pr-4 text-right text-slate-400">{r.call.delta.toFixed(2)}</td>
                      <td className="py-2.5 pr-4 text-right text-slate-300">{formatCurrency(r.call.premium)}</td>
                      <td className="py-2.5 pr-4 text-right text-emerald-400">{r.call.annualized_yield_pct.toFixed(1)}%</td>
                      <td className="py-2.5 text-right">
                        {r.est_annual_income != null ? (
                          <span className="text-emerald-400 font-medium">{formatCurrency(r.est_annual_income)}</span>
                        ) : (
                          <span className="text-slate-600 text-xs">&lt;100 shares</span>
                        )}
                      </td>
                    </>
                  ) : (
                    <td colSpan={6} className="py-2.5 text-right text-slate-600 text-xs">no options chain</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Performance: benchmark + sector exposure
// ---------------------------------------------------------------------------

function useBenchmark() {
  return useQuery({
    queryKey: ['quant', 'benchmark'],
    queryFn: () => api.getBenchmark(),
    staleTime: 15 * 60 * 1000,
    retry: 1,
  })
}

function useSectors() {
  return useQuery({
    queryKey: ['quant', 'sectors'],
    queryFn: api.getSectors,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
}

const SECTOR_BAR_COLORS = ['#38bdf8', '#34d399', '#a78bfa', '#f59e0b', '#fb7185', '#22d3ee', '#facc15', '#4ade80', '#f472b6', '#94a3b8', '#64748b', '#e2e8f0']

export function PerformanceTab() {
  const { data: bench, isLoading: benchLoading, error: benchError } = useBenchmark()
  const { data: sectors, isLoading: sectorsLoading } = useSectors()

  return (
    <div className="space-y-6">
      <Panel
        title="Portfolio vs SPY"
        sub="Time-weighted return from daily holdings snapshots — contributions don't inflate the line. Flows approximated from cost-basis changes."
      >
        {benchLoading ? (
          <Skeleton className="h-72" />
        ) : benchError || !bench ? (
          <p className="text-sm text-slate-500 py-6 text-center">
            {(benchError as any)?.message?.includes('400')
              ? 'Not enough daily snapshots yet — the comparison builds as Schwab sync runs each night.'
              : "Couldn't load benchmark data."}
          </p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider">Your Return</div>
                <div className={`text-lg font-bold ${bench.portfolio_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {bench.portfolio_return_pct >= 0 ? '+' : ''}{bench.portfolio_return_pct.toFixed(1)}%
                </div>
              </div>
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider">SPY</div>
                <div className={`text-lg font-bold ${bench.spy_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {bench.spy_return_pct >= 0 ? '+' : ''}{bench.spy_return_pct.toFixed(1)}%
                </div>
              </div>
              <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                <div className="text-[11px] text-slate-500 uppercase tracking-wider">Excess</div>
                <div className={`text-lg font-bold ${bench.excess_return_pct >= 0 ? 'text-sky-400' : 'text-amber-400'}`}>
                  {bench.excess_return_pct >= 0 ? '+' : ''}{bench.excess_return_pct.toFixed(1)}%
                </div>
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={bench.series} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                  <XAxis dataKey="date" stroke="#64748b" fontSize={10} minTickGap={40}
                    tickFormatter={(d: string) => new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} />
                  <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']}
                    tickFormatter={(v: number) => `${(v - 100).toFixed(0)}%`} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number, name: string) => [`${(v - 100).toFixed(2)}%`, name === 'portfolio' ? 'Portfolio' : 'SPY']}
                  />
                  <Line dataKey="portfolio" name="portfolio" stroke="#38bdf8" strokeWidth={2} dot={false} />
                  <Line dataKey="spy" name="spy" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                  <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v: string) => v === 'portfolio' ? 'Portfolio' : 'SPY'} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[11px] text-slate-600 mt-2">{bench.n_snapshots} snapshots, {bench.start} → {bench.end}.</p>
          </>
        )}
      </Panel>

      <Panel
        title="Sector Exposure (Look-Through)"
        sub="ETF holdings decomposed into approximate sector weights from a static composition table — indicative, not exact."
      >
        {sectorsLoading ? (
          <Skeleton className="h-48" />
        ) : !sectors ? (
          <p className="text-sm text-slate-500">Couldn't load sector data.</p>
        ) : (
          <>
            <div className="flex h-5 rounded-full overflow-hidden mb-4">
              {sectors.sectors.map((s, i) => (
                <div
                  key={s.sector}
                  title={`${s.sector}: ${s.pct.toFixed(1)}%`}
                  style={{ width: `${s.pct}%`, background: SECTOR_BAR_COLORS[i % SECTOR_BAR_COLORS.length] }}
                />
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5">
              {sectors.sectors.map((s, i) => (
                <div key={s.sector} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 text-slate-300">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: SECTOR_BAR_COLORS[i % SECTOR_BAR_COLORS.length] }} />
                    {s.sector}
                  </span>
                  <span className="text-slate-400 tabular-nums">{s.pct.toFixed(1)}% · {formatCurrency(s.value)}</span>
                </div>
              ))}
            </div>
            {sectors.unclassified_pct > 10 && (
              <p className="text-xs text-amber-400/80 mt-3">
                {sectors.unclassified_pct.toFixed(0)}% of the portfolio isn't in the classification table — treat the rest as a partial picture.
              </p>
            )}
          </>
        )}
      </Panel>
    </div>
  )
}
