import { useEffect, useState } from 'react'
import Header from '../components/layout/Header'
import { useToast } from '../components/Toast'
import {
  useFireSettings, useUpdateFireSettings, useFireSummary, useFireMonteCarlo, useFireSwr,
} from '../hooks/useFire'
import { formatCurrency, formatPct } from '../utils/format'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { FireMonteCarloResponse, SwrResponse } from '../types'

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

function Stat({ label, value, tone = 'text-slate-100' }: { label: string; value: string; tone?: string }) {
  return (
    <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-bold ${tone}`}>{value}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inputs panel — settings persisted server-side
// ---------------------------------------------------------------------------

function InputsPanel() {
  const { data: settings } = useFireSettings()
  const update = useUpdateFireSettings()
  const toast = useToast()

  const [currentAge, setCurrentAge] = useState('')
  const [targetAge, setTargetAge] = useState('65')
  const [spend, setSpend] = useState('')
  const [rate, setRate] = useState('4.0')

  useEffect(() => {
    if (!settings) return
    if (settings.current_age != null) setCurrentAge(String(settings.current_age))
    if (settings.target_retirement_age != null) setTargetAge(String(settings.target_retirement_age))
    if (settings.expected_annual_spend != null) setSpend(String(settings.expected_annual_spend))
    setRate((settings.withdrawal_rate * 100).toFixed(2))
  }, [settings])

  const save = () => {
    update.mutate(
      {
        current_age: currentAge ? parseInt(currentAge) : undefined,
        target_retirement_age: targetAge ? parseInt(targetAge) : undefined,
        expected_annual_spend: spend ? parseFloat(spend) : undefined,
        withdrawal_rate: rate ? parseFloat(rate) / 100 : undefined,
      },
      {
        onSuccess: () => toast.success('FIRE assumptions saved'),
        onError: (e: any) => toast.error(e?.message ?? 'Could not save settings'),
      },
    )
  }

  return (
    <Panel title="Assumptions" sub="Drives every projection below. Saved to your account.">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Current age</label>
          <input type="number" min="0" max="120" value={currentAge} onChange={(e) => setCurrentAge(e.target.value)}
            placeholder="e.g. 34"
            className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Target retirement age</label>
          <input type="number" min="1" max="120" value={targetAge} onChange={(e) => setTargetAge(e.target.value)}
            className="w-28 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Expected annual spend in retirement ($)</label>
          <input type="number" min="0" step="1000" value={spend} onChange={(e) => setSpend(e.target.value)}
            placeholder="defaults to current spend"
            className="w-52 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Withdrawal rate (%)</label>
          <input type="number" min="1" max="20" step="0.1" value={rate} onChange={(e) => setRate(e.target.value)}
            className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500" />
        </div>
        <button
          onClick={save}
          disabled={update.isPending}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {update.isPending ? 'Saving...' : 'Save'}
        </button>
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Summary — net worth, savings rate, FI number, years-to-FI, coast gauge
// ---------------------------------------------------------------------------

function CoastGauge({ progressPct, coastNumber, coastAge, current }: {
  progressPct: number | null; coastNumber: number | null; coastAge: number | null; current: number;
}) {
  if (coastNumber == null) {
    return <p className="text-sm text-slate-500">Set your current age and target retirement age above to see your Coast-FIRE number.</p>
  }
  const pct = Math.max(0, Math.min(100, progressPct ?? 0))
  const reached = pct >= 100
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-500">Current invested: {formatCurrency(current)}</span>
        <span className="text-xs text-slate-500">Coast number: {formatCurrency(coastNumber)}</span>
      </div>
      <div className="h-4 bg-slate-900 rounded-full overflow-hidden border border-slate-700">
        <div
          className={`h-full rounded-full transition-all ${reached ? 'bg-emerald-500' : 'bg-sky-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-4">
        <div className={`text-sm font-semibold ${reached ? 'text-emerald-400' : 'text-sky-400'}`}>
          {pct.toFixed(0)}% of coast number
        </div>
        {reached ? (
          <div className="text-sm text-emerald-400">You've already coasted — no further contributions needed to hit your FI number by target age.</div>
        ) : coastAge != null ? (
          <div className="text-sm text-slate-400">Projected to coast at age <span className="text-slate-100 font-semibold">{coastAge}</span></div>
        ) : (
          <div className="text-sm text-slate-500">Won't coast before target retirement age at current savings rate.</div>
        )}
      </div>
    </div>
  )
}

function SummaryPanels() {
  const { data, isLoading, error } = useFireSummary()

  if (isLoading) return <Skeleton className="h-64" />
  if (error) {
    return (
      <Panel title="FIRE Summary">
        <p className="text-sm text-slate-500">{(error as any)?.message ?? 'Not enough data yet — link an account and sync balances.'}</p>
      </Panel>
    )
  }
  if (!data) return null

  return (
    <>
      <Panel title="Years to Financial Independence" sub={`FI number = ${formatCurrency(data.annual_retirement_spend)}/yr ÷ ${formatPct(data.withdrawal_rate * 100)} withdrawal rate.`}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="Net Worth" value={formatCurrency(data.net_worth.net_worth)} />
          <Stat label="Invested Assets" value={formatCurrency(data.current_invested_assets)} />
          <Stat label="Savings Rate" value={formatPct(data.savings.savings_rate * 100)} tone="text-emerald-400" />
          <Stat label="FI Number" value={formatCurrency(data.fi_number)} />
          <Stat label="Annual Savings" value={formatCurrency(data.savings.annual_savings)} />
          <Stat label="Expected Return" value={formatPct(data.expected_annual_return * 100)} />
          <Stat
            label="Years to FI (deterministic)"
            value={data.years_to_fi != null ? data.years_to_fi.toFixed(1) : '—'}
            tone="text-sky-400"
          />
          <Stat label="Retirement Spend" value={formatCurrency(data.annual_retirement_spend)} />
        </div>
      </Panel>

      <Panel title="Coast-FIRE" sub="The amount your current invested assets need to reach today so they grow to your FI number by your target retirement age with zero further contributions.">
        <CoastGauge
          progressPct={data.coast.progress_pct}
          coastNumber={data.coast.coast_number}
          coastAge={data.coast.coast_reached_age}
          current={data.current_invested_assets}
        />
      </Panel>
    </>
  )
}

// ---------------------------------------------------------------------------
// Monte Carlo years-to-FI fan chart
// ---------------------------------------------------------------------------

function MonteCarloPanel() {
  const monteCarlo = useFireMonteCarlo()
  const [result, setResult] = useState<FireMonteCarloResponse | null>(null)
  const toast = useToast()

  const run = () => {
    monteCarlo.mutate(
      { max_years: 50, n_sims: 2000 },
      { onSuccess: setResult, onError: (e: any) => toast.error(e?.message ?? "Couldn't run simulation") },
    )
  }

  return (
    <Panel
      title="Years-to-FI Monte Carlo"
      sub="Block-bootstrap simulation off your real current allocation (services.quant's engine), not generic market assumptions."
    >
      <button
        onClick={run}
        disabled={monteCarlo.isPending}
        className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 mb-4"
      >
        {monteCarlo.isPending ? 'Simulating...' : 'Run Simulation'}
      </button>

      {result && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-2">
            <Stat label="10th Percentile" value={`${result.years_to_fi_p10.toFixed(1)} yrs`} tone="text-emerald-400" />
            <Stat label="Median" value={`${result.years_to_fi_p50.toFixed(1)} yrs`} tone="text-sky-400" />
            <Stat label="90th Percentile" value={`${result.years_to_fi_p90.toFixed(1)} yrs`} tone="text-amber-400" />
            <Stat label={`Never by Y${result.max_years}`} value={formatPct(result.prob_never_by_cap * 100)} />
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {result.n_sims.toLocaleString()} simulations against {result.symbols.length} held symbol{result.symbols.length === 1 ? '' : 's'}.
            Target: {formatCurrency(result.fi_number)}.
          </p>
        </>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Projection fan chart (deterministic-style using MC percentiles, reusing
// the same visual language as the quant Monte Carlo panel)
// ---------------------------------------------------------------------------

function SwrPanel() {
  const swr = useFireSwr()
  const [result, setResult] = useState<SwrResponse | null>(null)
  const toast = useToast()

  const run = () => {
    swr.mutate(
      {},
      { onSuccess: setResult, onError: (e: any) => toast.error(e?.message ?? "Couldn't run stress test") },
    )
  }

  const horizons = result ? Array.from(new Set(result.table.map((r) => r.years))).sort((a, b) => a - b) : []
  const rates = result ? Array.from(new Set(result.table.map((r) => r.withdrawal_rate))).sort((a, b) => a - b) : []

  const chartData = result?.table
    .filter((r) => r.years === horizons[0])
    .map((r) => ({ rate: `${(r.withdrawal_rate * 100).toFixed(1)}%`, success: r.success_probability * 100 }))

  return (
    <Panel
      title="Safe Withdrawal Rate Stress Test"
      sub="Decumulation Monte Carlo — same block-bootstrap engine as accumulation, run in reverse against your real allocation."
    >
      <button
        onClick={run}
        disabled={swr.isPending}
        className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 mb-4"
      >
        {swr.isPending ? 'Running stress test...' : 'Run Stress Test'}
      </button>

      {result && (
        <>
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                  <th className="pb-2 pr-4">Withdrawal Rate</th>
                  {horizons.map((h) => (
                    <th key={h} className="pb-2 pr-4 text-right">{h}yr Success</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {rates.map((rate) => (
                  <tr key={rate} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-2.5 pr-4 font-medium text-slate-100">{(rate * 100).toFixed(1)}%</td>
                    {horizons.map((h) => {
                      const row = result.table.find((r) => r.withdrawal_rate === rate && r.years === h)
                      const p = row?.success_probability ?? 0
                      const tone = p >= 0.95 ? 'text-emerald-400' : p >= 0.85 ? 'text-amber-400' : 'text-rose-400'
                      return (
                        <td key={h} className={`py-2.5 pr-4 text-right font-semibold ${tone}`}>
                          {formatPct(p * 100, 0)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            {horizons.map((h) => {
              const safe = result.max_safe_rate_by_horizon[String(h)]
              return (
                <div key={h} className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider">{h}-Year Max Safe Rate</div>
                  <div className="text-sm text-slate-300 mt-1">
                    90% success: <span className="text-emerald-400 font-semibold">{safe ? formatPct(safe.rate_90 * 100, 1) : '—'}</span>
                  </div>
                  <div className="text-sm text-slate-300">
                    95% success: <span className="text-sky-400 font-semibold">{safe ? formatPct(safe.rate_95 * 100, 1) : '—'}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {chartData && chartData.length > 0 && (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 0, left: 10 }}>
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                  <XAxis dataKey="rate" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => `${v.toFixed(0)}%`}
                  />
                  <Area dataKey="success" name={`Success @ ${horizons[0]}yr`} stroke="#38bdf8" fill="#0ea5e9" fillOpacity={0.2} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="text-xs text-slate-500 mt-3">
            "Success" = balance never hits zero within the horizon, across {result.symbols.length} held symbol{result.symbols.length === 1 ? '' : 's'}.
          </p>
        </>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function FirePage() {
  return (
    <div className="space-y-6">
      <Header title="FIRE Projector" />
      <InputsPanel />
      <SummaryPanels />
      <MonteCarloPanel />
      <SwrPanel />
    </div>
  )
}
