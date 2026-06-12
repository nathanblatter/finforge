import { useState } from 'react'
import { usePriceAlerts, useCreatePriceAlert, useDeletePriceAlert } from '../../hooks/usePriceAlerts'
import { useToast } from '../Toast'
import { formatCurrency } from '../../utils/format'

export default function PriceAlertsPanel({ defaultSymbol = '' }: { defaultSymbol?: string }) {
  const { data, isLoading } = usePriceAlerts()
  const create = useCreatePriceAlert()
  const del = useDeletePriceAlert()
  const toast = useToast()

  const [symbol, setSymbol] = useState(defaultSymbol)
  const [direction, setDirection] = useState<'above' | 'below'>('below')
  const [threshold, setThreshold] = useState('')

  const alerts = data?.alerts ?? []

  const handleAdd = () => {
    const sym = symbol.trim().toUpperCase()
    const price = Number(threshold)
    if (!sym) { toast.error('Enter a symbol'); return }
    if (!price || price <= 0) { toast.error('Enter a positive price'); return }
    create.mutate(
      { symbol: sym, direction, threshold: price },
      {
        onSuccess: () => {
          toast.success(`Alert set for ${sym}`)
          setSymbol('')
          setThreshold('')
        },
        onError: (e: any) => toast.error(e?.message ?? 'Failed to create alert'),
      },
    )
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Price Alerts</h3>

      {/* Add form */}
      <div className="flex flex-wrap items-end gap-2 mb-4">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol"
          className="w-28 bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
        />
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value as 'above' | 'below')}
          className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          <option value="below">Drops below</option>
          <option value="above">Rises above</option>
        </select>
        <div className="flex items-center">
          <span className="text-slate-500 text-sm mr-1">$</span>
          <input
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            placeholder="0.00"
            className="w-28 bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
        </div>
        <button
          onClick={handleAdd}
          disabled={create.isPending}
          className="px-3 py-1.5 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          Add
        </button>
      </div>

      {/* Alert list */}
      {isLoading ? (
        <div className="space-y-2">{[...Array(2)].map((_, i) => <div key={i} className="h-9 bg-slate-700 animate-pulse rounded-lg" />)}</div>
      ) : alerts.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-4">No price alerts set.</p>
      ) : (
        <div className="space-y-1.5">
          {alerts.map((a) => (
            <div key={a.id} className="flex items-center justify-between px-3 py-2 bg-slate-900/50 rounded-lg text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-medium text-slate-200">{a.symbol}</span>
                <span className="text-slate-400">
                  {a.direction === 'above' ? 'rises above' : 'drops below'} {formatCurrency(a.threshold)}
                </span>
                {a.last_price != null && (
                  <span className="text-xs text-slate-500">· now {formatCurrency(a.last_price)}</span>
                )}
                {!a.is_active && (
                  <span className="text-[10px] uppercase tracking-wider text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">
                    Triggered
                  </span>
                )}
              </div>
              <button
                onClick={() => del.mutate(a.id, { onError: (e: any) => toast.error(e?.message ?? 'Failed to delete') })}
                aria-label={`Delete alert for ${a.symbol}`}
                className="text-slate-600 hover:text-rose-400 transition-colors flex-shrink-0"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
