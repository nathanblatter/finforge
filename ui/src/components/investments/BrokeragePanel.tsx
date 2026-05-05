import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { formatCurrency, formatPct } from '../../utils/format'
import { useQuotes } from '../../hooks/useMarketData'
import type { BrokerageResponse } from '../../types'

const COLORS = ['#38bdf8', '#818cf8', '#34d399', '#fb923c', '#f472b6', '#a78bfa', '#4ade80', '#fbbf24']

interface Props {
  data: BrokerageResponse
}

export default function BrokeragePanel({ data }: Props) {
  const symbols = data.holdings.map((h) => h.symbol).join(',')
  const { data: quotesData } = useQuotes(symbols)
  const quotes = quotesData?.quotes ?? {}
  const totalValue = Number(data.total_portfolio_value)
  const cashPosition = Number(data.cash_position)
  const investedPosition = Number(data.invested_position)

  const allocationData = [
    ...data.holdings.map((h) => ({ name: h.symbol, value: Number(h.market_value) })),
    ...(cashPosition > 0
      ? [{ name: 'Cash', value: cashPosition }]
      : []),
  ]

  return (
    <div className="space-y-6">
      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
            Portfolio Value
          </div>
          <div className="text-2xl font-bold text-sky-400">
            {formatCurrency(totalValue)}
          </div>
          {data.as_of && (
            <div className="text-xs text-slate-500 mt-1">as of {data.as_of}</div>
          )}
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
            Invested
          </div>
          <div className="text-2xl font-bold text-slate-100">
            {formatCurrency(investedPosition)}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {totalValue ? formatPct((investedPosition / totalValue) * 100) : '0.0%'} of portfolio
          </div>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
            Cash
          </div>
          <div className="text-2xl font-bold text-emerald-400">
            {formatCurrency(cashPosition)}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {totalValue ? formatPct((cashPosition / totalValue) * 100) : '0.0%'} of portfolio
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Allocation chart */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">Allocation</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={allocationData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                >
                  {allocationData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8' }}
                  itemStyle={{ color: '#f1f5f9' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Holdings table */}
        <div className="lg:col-span-2 bg-slate-800 border border-slate-700 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">Holdings</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4 text-right">Qty</th>
                  <th className="pb-2 pr-4 text-right">Market Value</th>
                  <th className="pb-2 pr-4 text-right">Price</th>
                  <th className="pb-2 pr-4 text-right">Day Chg</th>
                  <th className="pb-2 pr-4 text-right">Day %</th>
                  <th className="pb-2 pr-4 text-right">Unrealized P&L</th>
                  <th className="pb-2 text-right">% Portfolio</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {data.holdings.map((h) => {
                  const q = quotes[h.symbol]
                  const dayChange = q?.net_change ?? null
                  const dayPct = q?.net_change_pct ?? null
                  const isUp = (dayChange ?? 0) >= 0
                  const dayColor = isUp ? 'text-emerald-400' : 'text-rose-400'

                  return (
                    <tr key={h.symbol} className="hover:bg-slate-700/30 transition-colors">
                      <td className="py-2.5 pr-4 font-medium text-slate-100">{h.symbol}</td>
                      <td className="py-2.5 pr-4 text-right text-slate-400">
                        {Number(h.quantity).toFixed(4)}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-slate-200">
                        {formatCurrency(Number(h.market_value))}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-slate-200">
                        {q?.last_price != null ? formatCurrency(q.last_price) : '—'}
                      </td>
                      <td className={`py-2.5 pr-4 text-right ${dayColor}`}>
                        {dayChange != null
                          ? `${isUp ? '+' : ''}${Number(dayChange).toFixed(2)}`
                          : '—'}
                      </td>
                      <td className={`py-2.5 pr-4 text-right ${dayColor}`}>
                        {dayPct != null
                          ? `${isUp ? '+' : ''}${formatPct(dayPct)}`
                          : '—'}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        {h.unrealized_gain_loss != null ? (
                          <span className={Number(h.unrealized_gain_loss) >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                            {Number(h.unrealized_gain_loss) >= 0 ? '+' : ''}
                            {formatCurrency(Number(h.unrealized_gain_loss))}
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-2.5 text-right text-slate-400">
                        {formatPct(h.pct_of_portfolio)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
