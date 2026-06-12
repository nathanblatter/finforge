import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { formatCurrency, formatDate } from '../../utils/format'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function useBillsForecast() {
  return useQuery({
    queryKey: ['spending', 'bills-forecast'],
    queryFn: () => api.getBillsForecast(30),
    staleTime: 30 * 60 * 1000,
    retry: 1,
  })
}

export default function BillCalendar() {
  const { data, isLoading } = useBillsForecast()

  if (isLoading) return <Skeleton className="h-56" />
  if (!data || data.events.length === 0) return null

  const low = data.projected_low
  const lowTone =
    low == null ? null : low.balance < 0 ? 'rose' : low.balance < 500 ? 'amber' : null

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-slate-300">Upcoming Bills</h3>
        {data.checking_balance != null && (
          <span className="text-xs text-slate-500">
            checking now: <span className="text-slate-300">{formatCurrency(data.checking_balance)}</span>
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Next {data.days} days, predicted from recurring charges. Card charges appear on their usual
        charge date, not the statement payment date — treat the balance path as approximate.
      </p>

      {low != null && (
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className={`rounded-lg p-3 border ${
            lowTone === 'rose'
              ? 'bg-rose-500/10 border-rose-500/30'
              : lowTone === 'amber'
                ? 'bg-amber-500/10 border-amber-500/30'
                : 'bg-slate-900/60 border-slate-700'
          }`}>
            <div className="text-[11px] text-slate-500 uppercase tracking-wider">Projected Low</div>
            <div className={`text-lg font-bold ${
              lowTone === 'rose' ? 'text-rose-400' : lowTone === 'amber' ? 'text-amber-400' : 'text-slate-100'
            }`}>
              {formatCurrency(low.balance)}
            </div>
            <div className="text-[11px] text-slate-500">{formatDate(low.date)}</div>
          </div>
          <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
            <div className="text-[11px] text-slate-500 uppercase tracking-wider">End of Window</div>
            <div className={`text-lg font-bold ${
              (data.projected_end_balance ?? 0) >= (data.checking_balance ?? 0) ? 'text-emerald-400' : 'text-slate-100'
            }`}>
              {data.projected_end_balance != null ? formatCurrency(data.projected_end_balance) : '—'}
            </div>
            <div className="text-[11px] text-slate-500">{data.events.length} predicted events</div>
          </div>
        </div>
      )}

      {lowTone === 'rose' && (
        <p className="text-xs text-rose-400 mb-3">
          ⚠ Checking is projected to go negative before the window ends — a bill lands ahead of income.
        </p>
      )}

      <div className="overflow-x-auto max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-800">
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
              <th className="pb-2 pr-4">Due</th>
              <th className="pb-2 pr-4">Merchant</th>
              <th className="pb-2 pr-4 text-right">Amount</th>
              <th className="pb-2 text-right">Projected Balance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/50">
            {data.events.map((e, i) => (
              <tr key={`${e.merchant}-${e.date}-${i}`} className="hover:bg-slate-700/30 transition-colors">
                <td className="py-2 pr-4 text-slate-400 whitespace-nowrap">{formatDate(e.date)}</td>
                <td className="py-2 pr-4">
                  <Link
                    to={`/merchant?name=${encodeURIComponent(e.merchant)}`}
                    className="text-slate-200 hover:text-sky-400 transition-colors"
                  >
                    {e.merchant}
                  </Link>
                  {e.category && <span className="text-slate-600 text-xs ml-2">{e.category}</span>}
                </td>
                <td className={`py-2 pr-4 text-right tabular-nums ${e.kind === 'income' ? 'text-emerald-400' : 'text-slate-200'}`}>
                  {e.kind === 'income' ? '+' : ''}{formatCurrency(Math.abs(e.amount))}
                </td>
                <td className={`py-2 text-right tabular-nums ${
                  e.balance_after != null && e.balance_after < 0 ? 'text-rose-400' : 'text-slate-500'
                }`}>
                  {e.balance_after != null ? formatCurrency(e.balance_after) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
