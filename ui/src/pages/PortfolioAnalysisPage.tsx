import { useState } from 'react'
import Header from '../components/layout/Header'
import { usePortfolioAnalysis, usePortfolioTargets, useSetPortfolioTargets, useDrawdownPredictions, usePredictDrawdown } from '../hooks/usePortfolioAnalysis'
import { formatCurrency, formatPct } from '../utils/format'
import type { PortfolioTargetItem } from '../types'

type Tab = 'risk' | 'rebalance' | 'tlh' | 'drawdown'

const TABS: { label: string; value: Tab }[] = [
  { label: 'Risk & Allocation', value: 'risk' },
  { label: 'Rebalancing', value: 'rebalance' },
  { label: 'Tax-Loss Harvesting', value: 'tlh' },
  { label: 'Drawdown Risk', value: 'drawdown' },
]

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-xl font-bold text-slate-100">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function PortfolioAnalysisPage() {
  const [tab, setTab] = useState<Tab>('risk')
  const { data, isLoading } = usePortfolioAnalysis()
  const { data: targetsData } = usePortfolioTargets()
  const setTargets = useSetPortfolioTargets()
  const { data: ddData, isLoading: ddLoading } = useDrawdownPredictions()
  const predictDrawdown = usePredictDrawdown()
  const [predictSymbol, setPredictSymbol] = useState('')
  const [adhocResult, setAdhocResult] = useState<{ symbol: string; prob: number; risk: string } | null>(null)

  // Target editor state
  const [editTargets, setEditTargets] = useState<PortfolioTargetItem[]>([])
  const [editing, setEditing] = useState(false)
  const [newSym, setNewSym] = useState('')
  const [newPct, setNewPct] = useState('')

  const m = data?.portfolio_metrics
  const holdings = data?.holdings ?? []
  const rebalance = data?.rebalance_actions ?? []
  const tlh = data?.tlh_candidates ?? []

  const startEditing = () => {
    setEditTargets(targetsData?.targets?.map(t => ({ ...t })) ?? [])
    setEditing(true)
  }

  const saveTargets = () => {
    setTargets.mutate(
      { accountAlias: 'Schwab Brokerage', targets: editTargets },
      { onSuccess: () => setEditing(false) }
    )
  }

  const addTarget = () => {
    const sym = newSym.trim().toUpperCase()
    const pct = parseFloat(newPct)
    if (!sym || isNaN(pct) || pct <= 0) return
    if (editTargets.find(t => t.symbol === sym)) return
    setEditTargets([...editTargets, { symbol: sym, target_pct: pct }])
    setNewSym('')
    setNewPct('')
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Portfolio Analysis" />
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

      {isLoading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : !data?.analysis_date ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No analysis data yet.</p>
          <p className="text-slate-500 text-xs mt-1">Run cron jobs from Settings to generate portfolio analysis.</p>
        </div>
      ) : (
        <>
          {/* ============ RISK & ALLOCATION ============ */}
          {tab === 'risk' && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  label="Concentration (HHI)"
                  value={m?.hhi != null ? Math.round(Number(m.hhi)).toLocaleString() : '—'}
                  sub={m?.hhi != null ? (Number(m.hhi) < 1500 ? 'Diversified' : Number(m.hhi) < 2500 ? 'Moderate' : 'Concentrated') : undefined}
                />
                <MetricCard
                  label="Top 5 Holdings"
                  value={m?.top5_concentration != null ? formatPct(Number(m.top5_concentration)) : '—'}
                />
                <MetricCard
                  label="Weighted Volatility"
                  value={m?.weighted_volatility != null ? formatPct(Number(m.weighted_volatility) * 100) : '—'}
                  sub="Annualized"
                />
                <MetricCard
                  label="Max Drawdown"
                  value={m?.max_drawdown != null ? formatPct(Number(m.max_drawdown) * 100) : '—'}
                  sub="From 52-week high"
                />
              </div>

              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-slate-300 mb-4">Holdings Risk Analysis</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                        <th className="pb-2 pr-4">Symbol</th>
                        <th className="pb-2 pr-4 text-right">Value</th>
                        <th className="pb-2 pr-4 text-right">% Port</th>
                        <th className="pb-2 pr-4 text-right">Volatility</th>
                        <th className="pb-2 pr-4 text-right">Beta</th>
                        <th className="pb-2 pr-4 text-right">Drawdown</th>
                        <th className="pb-2 text-right">P&L</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/50">
                      {holdings.map((h) => (
                        <tr key={h.symbol} className="hover:bg-slate-700/30 transition-colors">
                          <td className="py-2.5 pr-4 font-medium text-slate-100">{h.symbol}</td>
                          <td className="py-2.5 pr-4 text-right text-slate-200">
                            {h.market_value != null ? formatCurrency(h.market_value) : '—'}
                          </td>
                          <td className="py-2.5 pr-4 text-right text-slate-400">
                            {h.pct_of_portfolio != null ? formatPct(h.pct_of_portfolio) : '—'}
                          </td>
                          <td className="py-2.5 pr-4 text-right text-slate-400">
                            {h.annualized_vol != null ? formatPct(Number(h.annualized_vol) * 100) : '—'}
                          </td>
                          <td className="py-2.5 pr-4 text-right text-slate-400">
                            {h.beta != null ? Number(h.beta).toFixed(2) : '—'}
                          </td>
                          <td className="py-2.5 pr-4 text-right">
                            {h.drawdown_from_high != null ? (
                              <span className={Number(h.drawdown_from_high) < -0.1 ? 'text-rose-400' : 'text-slate-400'}>
                                {formatPct(Number(h.drawdown_from_high) * 100)}
                              </span>
                            ) : '—'}
                          </td>
                          <td className="py-2.5 text-right">
                            {h.unrealized_gl != null ? (
                              <span className={Number(h.unrealized_gl) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                {Number(h.unrealized_gl) >= 0 ? '+' : ''}{formatCurrency(h.unrealized_gl)}
                              </span>
                            ) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ============ REBALANCING ============ */}
          {tab === 'rebalance' && (
            <div className="space-y-6">
              {/* Target editor */}
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-300">Target Allocations</h3>
                  {!editing ? (
                    <button
                      onClick={startEditing}
                      className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
                    >
                      Edit Targets
                    </button>
                  ) : (
                    <div className="flex gap-2">
                      <button
                        onClick={saveTargets}
                        disabled={setTargets.isPending}
                        className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors disabled:opacity-50"
                      >
                        {setTargets.isPending ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        onClick={() => setEditing(false)}
                        className="px-3 py-1.5 text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>

                {editing ? (
                  <div className="space-y-3">
                    {editTargets.map((t, i) => (
                      <div key={t.symbol} className="flex items-center gap-3">
                        <span className="text-sm font-medium text-slate-200 w-24">{t.symbol}</span>
                        <input
                          type="number"
                          step="0.5"
                          min="0"
                          max="100"
                          value={t.target_pct}
                          onChange={(e) => {
                            const next = [...editTargets]
                            next[i] = { ...t, target_pct: parseFloat(e.target.value) || 0 }
                            setEditTargets(next)
                          }}
                          className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100 text-right focus:outline-none focus:border-sky-500"
                        />
                        <span className="text-xs text-slate-500">%</span>
                        <button
                          onClick={() => setEditTargets(editTargets.filter((_, j) => j !== i))}
                          className="text-xs text-rose-400 hover:text-rose-300"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <div className="flex items-center gap-2 pt-2 border-t border-slate-700">
                      <input
                        type="text"
                        placeholder="Symbol"
                        value={newSym}
                        onChange={(e) => setNewSym(e.target.value)}
                        className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                      />
                      <input
                        type="number"
                        step="0.5"
                        placeholder="%"
                        value={newPct}
                        onChange={(e) => setNewPct(e.target.value)}
                        className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-sm text-slate-100 text-right focus:outline-none focus:border-sky-500"
                      />
                      <button onClick={addTarget} className="text-xs text-sky-400 hover:text-sky-300">Add</button>
                    </div>
                    <div className="text-xs text-slate-500">
                      Total: {editTargets.reduce((s, t) => s + (t.target_pct || 0), 0).toFixed(1)}%
                      {' '}(remainder = cash)
                    </div>
                  </div>
                ) : (
                  targetsData?.targets && targetsData.targets.length > 0 ? (
                    <div className="space-y-1.5">
                      {targetsData.targets.map((t) => (
                        <div key={t.symbol} className="flex items-center justify-between text-sm">
                          <span className="text-slate-300">{t.symbol}</span>
                          <span className="text-slate-400">{formatPct(t.target_pct)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">No targets set. Click "Edit Targets" to define your desired allocation.</p>
                  )
                )}
              </div>

              {/* Drift table */}
              {rebalance.length > 0 && (
                <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-slate-300 mb-4">Rebalancing Actions</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                          <th className="pb-2 pr-4">Symbol</th>
                          <th className="pb-2 pr-4 text-right">Current %</th>
                          <th className="pb-2 pr-4 text-right">Target %</th>
                          <th className="pb-2 pr-4 text-right">Drift</th>
                          <th className="pb-2 pr-4 text-center">Action</th>
                          <th className="pb-2 text-right">Trade Value</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-700/50">
                        {rebalance.map((r) => {
                          const driftColor = r.action === 'HOLD' ? 'text-slate-400'
                            : r.action === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                          const actionBg = r.action === 'HOLD' ? 'bg-slate-700 text-slate-400'
                            : r.action === 'BUY' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                          return (
                            <tr key={r.symbol} className="hover:bg-slate-700/30 transition-colors">
                              <td className="py-2.5 pr-4 font-medium text-slate-100">{r.symbol}</td>
                              <td className="py-2.5 pr-4 text-right text-slate-300">{formatPct(r.current_pct)}</td>
                              <td className="py-2.5 pr-4 text-right text-slate-400">{formatPct(r.target_pct)}</td>
                              <td className={`py-2.5 pr-4 text-right ${driftColor}`}>
                                {Number(r.drift_pct) >= 0 ? '+' : ''}{formatPct(r.drift_pct)}
                              </td>
                              <td className="py-2.5 pr-4 text-center">
                                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${actionBg}`}>
                                  {r.action}
                                </span>
                              </td>
                              <td className="py-2.5 text-right text-slate-300">
                                {r.action !== 'HOLD' ? formatCurrency(r.suggested_trade_value) : '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ============ TAX-LOSS HARVESTING ============ */}
          {tab === 'tlh' && (
            <div className="space-y-6">
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-slate-300 mb-1">Tax-Loss Harvesting Candidates</h3>
                <p className="text-xs text-slate-500 mb-4">
                  Positions with unrealized losses over $100 in your taxable brokerage account.
                  Uses aggregate cost basis (not per-lot).
                </p>

                {tlh.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-slate-400 text-sm">No tax-loss harvesting opportunities right now.</p>
                    <p className="text-slate-600 text-xs mt-1">Positions need unrealized losses exceeding $100 to appear here.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                          <th className="pb-2 pr-4">Symbol</th>
                          <th className="pb-2 pr-4 text-right">Market Value</th>
                          <th className="pb-2 pr-4 text-right">Cost Basis</th>
                          <th className="pb-2 pr-4 text-right">Unrealized Loss</th>
                          <th className="pb-2 text-center">Wash Sale Risk</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-700/50">
                        {tlh.map((t) => {
                          let washDetails: { date: string; action: string; amount: number }[] = []
                          if (t.wash_sale_details) {
                            try { washDetails = JSON.parse(t.wash_sale_details) } catch {}
                          }
                          return (
                            <tr key={t.symbol} className="hover:bg-slate-700/30 transition-colors">
                              <td className="py-2.5 pr-4 font-medium text-slate-100">{t.symbol}</td>
                              <td className="py-2.5 pr-4 text-right text-slate-300">{formatCurrency(t.market_value)}</td>
                              <td className="py-2.5 pr-4 text-right text-slate-400">{formatCurrency(t.cost_basis)}</td>
                              <td className="py-2.5 pr-4 text-right text-rose-400">
                                {formatCurrency(t.unrealized_gl)}
                              </td>
                              <td className="py-2.5 text-center">
                                {t.wash_sale_risk ? (
                                  <div>
                                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                      Warning
                                    </span>
                                    {washDetails.length > 0 && (
                                      <div className="mt-1.5 text-xs text-slate-500">
                                        {washDetails.map((d, i) => (
                                          <div key={i}>{d.action} on {d.date}</div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-emerald-400">Clear</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="bg-amber-950/30 border border-amber-500/20 rounded-xl p-4">
                <p className="text-xs text-amber-400/80">
                  <strong>Disclaimer:</strong> This is informational only, not tax advice. Tax-loss harvesting
                  analysis uses aggregate cost basis, not per-lot. Wash sale detection covers the last 30 days
                  of trading history. Consult a tax professional before making decisions.
                </p>
              </div>
            </div>
          )}

          {/* ============ DRAWDOWN RISK ============ */}
          {tab === 'drawdown' && (
            <div className="space-y-6">
              {/* Model info */}
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                <MetricCard
                  label="Model AUC"
                  value={ddData?.model_auc != null ? Number(ddData.model_auc).toFixed(3) : '—'}
                  sub="Validation ROC-AUC"
                />
                <MetricCard
                  label="Last Trained"
                  value={ddData?.model_trained_at
                    ? new Date(ddData.model_trained_at).toLocaleDateString()
                    : 'Not trained'}
                />
                <MetricCard
                  label="Predictions"
                  value={String(ddData?.predictions?.length ?? 0)}
                  sub="Cached for today"
                />
              </div>

              {/* Ad-hoc prediction */}
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-slate-300 mb-3">Predict Any Symbol</h3>
                <div className="flex gap-2 items-center">
                  <input
                    type="text"
                    value={predictSymbol}
                    onChange={(e) => setPredictSymbol(e.target.value.toUpperCase())}
                    placeholder="e.g. AAPL"
                    className="w-32 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && predictSymbol.trim()) {
                        predictDrawdown.mutate(predictSymbol.trim(), {
                          onSuccess: (d) => setAdhocResult({ symbol: d.symbol, prob: d.drawdown_probability, risk: d.risk_level }),
                        })
                      }
                    }}
                  />
                  <button
                    onClick={() => {
                      if (predictSymbol.trim()) {
                        predictDrawdown.mutate(predictSymbol.trim(), {
                          onSuccess: (d) => setAdhocResult({ symbol: d.symbol, prob: d.drawdown_probability, risk: d.risk_level }),
                        })
                      }
                    }}
                    disabled={predictDrawdown.isPending || !predictSymbol.trim()}
                    className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                  >
                    {predictDrawdown.isPending ? 'Running...' : 'Predict'}
                  </button>
                  {adhocResult && (
                    <div className="flex items-center gap-3 ml-4">
                      <span className="text-sm font-medium text-slate-100">{adhocResult.symbol}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              adhocResult.prob < 0.2 ? 'bg-emerald-500' :
                              adhocResult.prob < 0.4 ? 'bg-amber-500' :
                              adhocResult.prob < 0.6 ? 'bg-orange-500' : 'bg-rose-500'
                            }`}
                            style={{ width: `${adhocResult.prob * 100}%` }}
                          />
                        </div>
                        <span className="text-sm text-slate-300">{(adhocResult.prob * 100).toFixed(1)}%</span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          adhocResult.risk === 'LOW' ? 'bg-emerald-500/15 text-emerald-400' :
                          adhocResult.risk === 'MODERATE' ? 'bg-amber-500/15 text-amber-400' :
                          adhocResult.risk === 'HIGH' ? 'bg-orange-500/15 text-orange-400' :
                          'bg-rose-500/15 text-rose-400'
                        }`}>{adhocResult.risk}</span>
                      </div>
                    </div>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-2">
                  Probability that this symbol drops &gt;5% from current price within 30 days.
                </p>
              </div>

              {/* Holdings predictions table */}
              <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-300">Holdings Drawdown Risk</h3>
                  {ddData?.predictions && ddData.predictions.length === 0 && (
                    <span className="text-xs text-slate-500">Run predictions using the input above</span>
                  )}
                </div>

                {ddLoading ? (
                  <div className="space-y-2">
                    {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-8" />)}
                  </div>
                ) : !ddData?.predictions || ddData.predictions.length === 0 ? (
                  <p className="text-sm text-slate-500 text-center py-8">
                    No predictions cached for today. Use "Predict Any Symbol" above or run the drawdown model training from Settings.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                          <th className="pb-2 pr-4">Symbol</th>
                          <th className="pb-2 pr-4">Drawdown Probability</th>
                          <th className="pb-2 pr-4 text-center">Risk Level</th>
                          <th className="pb-2 text-right">Predicted</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-700/50">
                        {[...ddData.predictions]
                          .sort((a, b) => b.drawdown_probability - a.drawdown_probability)
                          .map((p) => {
                            const prob = Number(p.drawdown_probability)
                            const barColor = prob < 0.2 ? 'bg-emerald-500' :
                              prob < 0.4 ? 'bg-amber-500' : prob < 0.6 ? 'bg-orange-500' : 'bg-rose-500'
                            const badgeColor = p.risk_level === 'LOW' ? 'bg-emerald-500/15 text-emerald-400' :
                              p.risk_level === 'MODERATE' ? 'bg-amber-500/15 text-amber-400' :
                              p.risk_level === 'HIGH' ? 'bg-orange-500/15 text-orange-400' :
                              'bg-rose-500/15 text-rose-400'

                            return (
                              <tr key={p.symbol} className="hover:bg-slate-700/30 transition-colors">
                                <td className="py-2.5 pr-4 font-medium text-slate-100">{p.symbol}</td>
                                <td className="py-2.5 pr-4">
                                  <div className="flex items-center gap-2">
                                    <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${prob * 100}%` }} />
                                    </div>
                                    <span className="text-slate-300 tabular-nums">{(prob * 100).toFixed(1)}%</span>
                                  </div>
                                </td>
                                <td className="py-2.5 pr-4 text-center">
                                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badgeColor}`}>
                                    {p.risk_level}
                                  </span>
                                </td>
                                <td className="py-2.5 text-right text-slate-500 text-xs">{p.prediction_date}</td>
                              </tr>
                            )
                          })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="bg-slate-900/50 border border-slate-700 rounded-xl p-4">
                <p className="text-xs text-slate-500">
                  <strong>Model:</strong> GradientBoostingClassifier trained on ~50 large-cap symbols using 1-year daily price history.
                  Features: RSI, SMA ratios, Bollinger position, momentum, volatility, volume, drawdown, P/E, dividend yield.
                  Predicts probability of a &gt;5% drawdown within 30 calendar days. Retrained weekly.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
