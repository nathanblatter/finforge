import { useState, useMemo } from 'react'
import { useOptionsChain } from '../../hooks/useMarketData'
import { formatCurrency } from '../../utils/format'
import type { OptionContract } from '../../types'

interface Props {
  symbol: string
  onClose: () => void
}

export default function OptionsChainModal({ symbol, onClose }: Props) {
  const { data, isLoading, error } = useOptionsChain(symbol)
  const [tab, setTab] = useState<'CALL' | 'PUT'>('CALL')
  const [selectedExpiry, setSelectedExpiry] = useState<string | null>(null)

  const expiryMap = tab === 'CALL' ? data?.callExpDateMap : data?.putExpDateMap

  const expiryDates = useMemo(() => {
    if (!expiryMap) return []
    return Object.keys(expiryMap).sort()
  }, [expiryMap])

  const activeExpiry = selectedExpiry ?? expiryDates[0] ?? null

  const contracts: OptionContract[] = useMemo(() => {
    if (!expiryMap || !activeExpiry) return []
    const strikeMap = expiryMap[activeExpiry]
    if (!strikeMap) return []
    return Object.values(strikeMap).flat()
  }, [expiryMap, activeExpiry])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-bold text-slate-100">{symbol} Options Chain</h2>
            <p className="text-xs text-slate-500 mt-0.5">Real-time from Schwab</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-6 pt-4">
          {(['CALL', 'PUT'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === t
                  ? 'bg-sky-600 text-white'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-slate-200'
              }`}
            >
              {t}s
            </button>
          ))}
        </div>

        {/* Expiry selector */}
        {expiryDates.length > 0 && (
          <div className="px-6 pt-3">
            <select
              value={activeExpiry ?? ''}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
            >
              {expiryDates.map((exp) => (
                <option key={exp} value={exp}>
                  {exp.split(':')[0]}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {isLoading ? (
            <div className="text-slate-500 text-sm text-center py-12">Loading options chain...</div>
          ) : error ? (
            <div className="text-rose-400 text-sm text-center py-12">Failed to load options chain</div>
          ) : contracts.length === 0 ? (
            <div className="text-slate-500 text-sm text-center py-12">No contracts available</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                  <th className="pb-2 pr-4">Strike</th>
                  <th className="pb-2 pr-4 text-right">Bid</th>
                  <th className="pb-2 pr-4 text-right">Ask</th>
                  <th className="pb-2 pr-4 text-right">Last</th>
                  <th className="pb-2 pr-4 text-right">Volume</th>
                  <th className="pb-2 text-right">OI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {contracts.map((c, i) => (
                  <tr
                    key={i}
                    className={`hover:bg-slate-700/30 transition-colors ${
                      c.inTheMoney ? 'bg-sky-900/10' : ''
                    }`}
                  >
                    <td className="py-2 pr-4 font-medium text-slate-100">
                      {Number(c.strikePrice).toFixed(2)}
                      {c.inTheMoney && (
                        <span className="ml-1.5 text-[10px] text-sky-400 font-normal">ITM</span>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-right text-slate-300">{formatCurrency(c.bid)}</td>
                    <td className="py-2 pr-4 text-right text-slate-300">{formatCurrency(c.ask)}</td>
                    <td className="py-2 pr-4 text-right text-slate-200">{formatCurrency(c.last)}</td>
                    <td className="py-2 pr-4 text-right text-slate-400">{c.totalVolume?.toLocaleString() ?? '—'}</td>
                    <td className="py-2 text-right text-slate-400">{c.openInterest?.toLocaleString() ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
