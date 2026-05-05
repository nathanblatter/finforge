import { useState } from 'react'
import { formatCurrency, formatPct } from '../../utils/format'
import type { Watchlist } from '../../types'
import { useAddSymbol, useRemoveSymbol } from '../../hooks/useMarketData'

interface Props {
  watchlist: Watchlist
  onOptionsClick: (symbol: string) => void
}

export default function WatchlistPanel({ watchlist, onOptionsClick }: Props) {
  const [newSymbol, setNewSymbol] = useState('')
  const addSymbol = useAddSymbol()
  const removeSymbol = useRemoveSymbol()

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const sym = newSymbol.trim().toUpperCase()
    if (!sym) return
    addSymbol.mutate({ id: watchlist.id, symbol: sym })
    setNewSymbol('')
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">{watchlist.name}</h3>
        <span className="text-xs text-slate-500">{watchlist.items.length} symbols</span>
      </div>

      {/* Add symbol input */}
      <form onSubmit={handleAdd} className="flex gap-2 mb-4">
        <input
          type="text"
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value)}
          placeholder="Add symbol..."
          className="flex-1 bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
        />
        <button
          type="submit"
          disabled={addSymbol.isPending}
          className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          Add
        </button>
      </form>

      {/* Quote grid */}
      {watchlist.items.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">No symbols yet</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-4">Symbol</th>
                <th className="pb-2 pr-4 text-right">Price</th>
                <th className="pb-2 pr-4 text-right">Change</th>
                <th className="pb-2 pr-4 text-right">% Change</th>
                <th className="pb-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {watchlist.items.map((item) => {
                const q = item.quote
                const change = q?.net_change ?? 0
                const changePct = q?.net_change_pct ?? 0
                const isPositive = change >= 0
                const colorClass = isPositive ? 'text-emerald-400' : 'text-rose-400'

                return (
                  <tr key={item.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-2.5 pr-4 font-medium text-slate-100">{item.symbol}</td>
                    <td className="py-2.5 pr-4 text-right text-slate-200">
                      {q?.last_price != null ? formatCurrency(q.last_price) : '—'}
                    </td>
                    <td className={`py-2.5 pr-4 text-right ${colorClass}`}>
                      {q?.net_change != null
                        ? `${isPositive ? '+' : ''}${Number(change).toFixed(2)}`
                        : '—'}
                    </td>
                    <td className={`py-2.5 pr-4 text-right ${colorClass}`}>
                      {q?.net_change_pct != null
                        ? `${isPositive ? '+' : ''}${formatPct(changePct)}`
                        : '—'}
                    </td>
                    <td className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => onOptionsClick(item.symbol)}
                          className="text-xs text-sky-400 hover:text-sky-300 transition-colors"
                        >
                          Options
                        </button>
                        <button
                          onClick={() => removeSymbol.mutate({ id: watchlist.id, symbol: item.symbol })}
                          className="text-xs text-slate-500 hover:text-rose-400 transition-colors"
                        >
                          Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
