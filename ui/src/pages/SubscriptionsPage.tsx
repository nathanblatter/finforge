import { useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/layout/Header'
import { useSubscriptions } from '../hooks/useSpending'
import { formatCurrency, formatDate } from '../utils/format'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function SubscriptionsPage() {
  const [months, setMonths] = useState(6)
  const { data, isLoading } = useSubscriptions(months)

  const subs = data?.subscriptions ?? []

  return (
    <div className="space-y-6 max-w-[900px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Subscriptions" />
        <select
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          <option value={6}>Last 6 months</option>
          <option value={12}>Last 12 months</option>
          <option value={3}>Last 3 months</option>
        </select>
      </div>

      <p className="text-sm text-slate-500 -mt-2">
        Recurring charges detected from merchants that appear in 3+ months with consistent amounts.
      </p>

      {isLoading ? (
        <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : subs.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No recurring charges detected.</p>
          <p className="text-slate-500 text-xs mt-1">A merchant needs to appear across at least 3 months.</p>
        </div>
      ) : (
        <>
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Estimated monthly total</div>
            <div className="text-2xl font-bold text-sky-400">{formatCurrency(data!.monthly_total)}</div>
            <div className="text-xs text-slate-500 mt-1">{subs.length} recurring {subs.length === 1 ? 'charge' : 'charges'}</div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                    <th className="pb-2 pr-4">Merchant</th>
                    <th className="pb-2 pr-4">Category</th>
                    <th className="pb-2 pr-4 text-right">Monthly</th>
                    <th className="pb-2 pr-4 text-center">Months</th>
                    <th className="pb-2 text-right">Last charge</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {subs.map((s) => (
                    <tr key={s.merchant} className="hover:bg-slate-700/30 transition-colors">
                      <td className="py-2.5 pr-4 font-medium text-slate-100">
                        <Link
                          to={`/merchant?name=${encodeURIComponent(s.merchant)}`}
                          className="hover:text-sky-400 transition-colors"
                        >
                          {s.merchant}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4 text-slate-400">{s.category ?? '—'}</td>
                      <td className="py-2.5 pr-4 text-right text-slate-200">{formatCurrency(s.monthly_amount)}</td>
                      <td className="py-2.5 pr-4 text-center text-slate-400">{s.months_seen}</td>
                      <td className="py-2.5 text-right text-slate-500 whitespace-nowrap">{formatDate(s.last_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
