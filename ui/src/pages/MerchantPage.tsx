import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'
import { formatCurrency, formatDate } from '../utils/format'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className="text-lg font-bold text-slate-100">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function MerchantPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const name = params.get('name') ?? ''

  const { data, isLoading, error } = useQuery({
    queryKey: ['merchant', name],
    queryFn: () => api.getMerchantDetail(name),
    enabled: name.length > 0,
    staleTime: 15 * 60 * 1000,
    retry: false,
  })

  if (!name) {
    return <p className="text-sm text-slate-500 py-12 text-center">No merchant specified.</p>
  }

  return (
    <div className="space-y-6 max-w-[1000px]">
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back
        </button>
        <h1 className="text-2xl font-bold text-slate-100">{data?.merchant ?? name}</h1>
        {data?.is_recurring && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/20">
            Recurring{data.monthly_median != null ? ` · ~${formatCurrency(data.monthly_median)}/mo` : ''}
          </span>
        )}
        {data?.category && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20">
            {data.category}{data.has_rule ? ' (rule)' : ''}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-20" />)}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : error || !data ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No history found for "{name}".</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat label="Total Spent" value={formatCurrency(data.total_spent)} sub={`since ${formatDate(data.first_seen)}`} />
            <Stat label="Visits" value={String(data.visits)} sub={`last: ${formatDate(data.last_seen)}`} />
            <Stat label="Average Charge" value={formatCurrency(data.avg_amount)} />
            <Stat label="Accounts" value={data.accounts.join(', ') || '—'} />
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-1">Monthly Spend</h3>
            <p className="text-xs text-slate-500 mb-4">Trailing 12 months at this merchant.</p>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.trend} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="month" stroke="#64748b" fontSize={10}
                    tickFormatter={(m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString('en-US', { month: 'short' })}
                  />
                  <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: number) => formatCurrency(v)}
                    labelFormatter={(m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                  />
                  <Bar dataKey="total" name="Spent" fill="#38bdf8" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Recent Transactions</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Category</th>
                  <th className="pb-2 pr-4">Account</th>
                  <th className="pb-2 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {data.recent.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-700/30 transition-colors">
                    <td className="py-2.5 pr-4 text-slate-400 whitespace-nowrap">{formatDate(t.date)}</td>
                    <td className="py-2.5 pr-4 text-slate-400">{t.category ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-slate-400">{t.account_alias}</td>
                    <td className="py-2.5 text-right font-medium">
                      <span className={t.amount < 0 ? 'text-emerald-400' : 'text-slate-100'}>
                        {formatCurrency(Math.abs(t.amount))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
