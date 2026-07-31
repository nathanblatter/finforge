import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/layout/Header'
import RunwayChart from '../components/cashflow/RunwayChart'
import { useToast } from '../components/Toast'
import { useRunway, useCashflowSettings, useUpdateCashflowSettings } from '../hooks/useCashflow'
import { formatCurrency, formatDate } from '../utils/format'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

const RANGE_OPTIONS = [
  { label: '60D', days: 60 },
  { label: '90D', days: 90 },
  { label: '120D', days: 120 },
]

export default function RunwayPage() {
  const [days, setDays] = useState(90)
  const { data, isLoading } = useRunway(days)
  const { data: settings } = useCashflowSettings()
  const updateSettings = useUpdateCashflowSettings()
  const toast = useToast()

  const [floorInput, setFloorInput] = useState('')
  const [leadTimeInput, setLeadTimeInput] = useState('')
  const [editingSettings, setEditingSettings] = useState(false)

  useEffect(() => {
    if (settings && !editingSettings) {
      setFloorInput(String(settings.floor_amount))
      setLeadTimeInput(String(settings.lead_time_days))
    }
  }, [settings, editingSettings])

  const handleSaveSettings = () => {
    const floor = Number(floorInput)
    const lead = Number(leadTimeInput)
    if (!Number.isFinite(floor) || floor < 0) { toast.error('Enter a valid floor amount'); return }
    if (!Number.isInteger(lead) || lead < 1) { toast.error('Enter a valid lead time (days)'); return }
    updateSettings.mutate(
      { floorAmount: floor, leadTimeDays: lead },
      {
        onSuccess: () => {
          toast.success('Runway floor updated')
          setEditingSettings(false)
        },
        onError: (e: any) => toast.error(e?.message ?? 'Failed to save settings'),
      },
    )
  }

  const crossing = data?.crossing
  const riskCrossing = data?.earliest_risk_crossing

  return (
    <div className="space-y-6 max-w-[1100px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Cash-Flow Runway" />
        <div className="flex gap-1">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.days}
              onClick={() => setDays(opt.days)}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                days === opt.days
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-500 -mt-4">
        Projects checking against detected recurring bills, income, and a confidence band from
        historical discretionary spend. Approximate — card charges land on their charge date, not
        the statement date.
      </p>

      {/* Floor setting */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-300">Balance floor</h3>
          {!editingSettings && (
            <button
              onClick={() => setEditingSettings(true)}
              className="text-xs text-slate-400 hover:text-sky-400 transition-colors"
            >
              Edit
            </button>
          )}
        </div>
        {editingSettings ? (
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-40">
              <label className="block text-xs text-slate-400 mb-1">Floor amount</label>
              <div className="flex items-center">
                <span className="text-slate-500 text-sm mr-1">$</span>
                <input
                  type="number"
                  value={floorInput}
                  onChange={(e) => setFloorInput(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>
            <div className="w-40">
              <label className="block text-xs text-slate-400 mb-1">Alert lead time (days)</label>
              <input
                type="number"
                value={leadTimeInput}
                onChange={(e) => setLeadTimeInput(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
              />
            </div>
            <button
              onClick={handleSaveSettings}
              disabled={updateSettings.isPending}
              className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {updateSettings.isPending ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => setEditingSettings(false)}
              className="px-4 py-2 text-sm font-medium bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <p className="text-sm text-slate-300">
            Alert me if checking is on track to drop below{' '}
            <span className="text-slate-100 font-medium">{formatCurrency(settings?.floor_amount ?? 0)}</span>{' '}
            within <span className="text-slate-100 font-medium">{settings?.lead_time_days ?? 14} days</span>.
          </p>
        )}
      </div>

      {isLoading ? (
        <Skeleton className="h-80" />
      ) : !data ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">Couldn't load the runway forecast.</p>
        </div>
      ) : data.checking_balance == null ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No checking balance data yet.</p>
          <p className="text-slate-500 text-xs mt-1">The runway builds once a checking account is synced.</p>
        </div>
      ) : (
        <>
          {/* Callouts */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
              <div className="text-[11px] text-slate-500 uppercase tracking-wider">Checking now</div>
              <div className="text-lg font-bold text-slate-100">{formatCurrency(data.checking_balance)}</div>
            </div>
            <div className={`rounded-lg p-3 border ${
              crossing ? 'bg-rose-500/10 border-rose-500/30' : 'bg-slate-900/60 border-slate-700'
            }`}>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider">Projected floor crossing</div>
              {crossing ? (
                <>
                  <div className="text-lg font-bold text-rose-400">{formatDate(crossing.date)}</div>
                  <div className="text-[11px] text-slate-500">{crossing.lead_time_days} day(s) from now</div>
                </>
              ) : (
                <div className="text-lg font-bold text-emerald-400">Not within {data.days}d</div>
              )}
            </div>
            <div className={`rounded-lg p-3 border ${
              riskCrossing ? 'bg-amber-500/10 border-amber-500/30' : 'bg-slate-900/60 border-slate-700'
            }`}>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider">Earliest risk (low band)</div>
              {riskCrossing ? (
                <>
                  <div className="text-lg font-bold text-amber-400">{formatDate(riskCrossing.date)}</div>
                  <div className="text-[11px] text-slate-500">{riskCrossing.lead_time_days} day(s) from now</div>
                </>
              ) : (
                <div className="text-lg font-bold text-emerald-400">Clear</div>
              )}
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-slate-300">Projected balance</h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Shaded band = discretionary-spend uncertainty (median{' '}
                {formatCurrency(data.daily_discretionary_median)}/day, widening over time).
              </p>
            </div>
            <RunwayChart series={data.series} floorAmount={data.floor_amount} days={data.days} />
          </div>

          {/* Driver events table */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Driver events</h3>
            {data.events.length === 0 ? (
              <p className="text-sm text-slate-500">No recurring bills or income detected yet.</p>
            ) : (
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-800">
                    <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4">Merchant</th>
                      <th className="pb-2 pr-4 text-right">Amount</th>
                      <th className="pb-2 text-right">Balance after</th>
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
                          e.balance_after != null && e.balance_after < data.floor_amount ? 'text-rose-400' : 'text-slate-500'
                        }`}>
                          {e.balance_after != null ? formatCurrency(e.balance_after) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
