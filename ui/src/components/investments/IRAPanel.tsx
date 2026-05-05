import { formatCurrency, formatPct } from '../../utils/format'
import type { IRAResponse } from '../../types'

function LockIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

interface Props {
  data: IRAResponse
}

export default function IRAPanel({ data }: Props) {
  const pct = Math.min(Number(data.contribution_pct_complete), 100)
  const historyToShow = data.contribution_history.slice(0, 5)

  return (
    <div className="border border-indigo-500/30 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-indigo-950/40 px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-indigo-400">
            <LockIcon />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-indigo-300">Schwab Roth IRA</h3>
            <p className="text-xs text-indigo-400/70">Retirement — Long-term</p>
          </div>
        </div>
        <span className="text-xs font-medium bg-indigo-500/20 text-indigo-300 px-2.5 py-1 rounded-full">
          Retirement Account
        </span>
      </div>

      <div className="bg-slate-800/60 p-5 space-y-5">
        {/* Balance + growth */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Current Balance</div>
            <div className="text-2xl font-bold text-indigo-300">
              {formatCurrency(data.current_balance)}
            </div>
            {data.as_of && (
              <div className="text-xs text-slate-600 mt-0.5">as of {data.as_of}</div>
            )}
          </div>
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">Growth</div>
            <div className={`text-2xl font-bold ${Number(data.growth_amount) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {Number(data.growth_amount) >= 0 ? '+' : ''}{formatCurrency(data.growth_amount)}
            </div>
            <div className="text-xs text-slate-600 mt-0.5">balance − contributions</div>
          </div>
        </div>

        {/* Contribution progress */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm text-slate-300">
              {formatCurrency(data.contributions_ytd)} contributed
            </span>
            <span className="text-xs text-indigo-400">
              2026 limit: $7,000
            </span>
          </div>
          <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-xs text-slate-500">{formatPct(pct, 0)} of limit</span>
            <span className="text-xs text-slate-500">
              {formatCurrency(data.contributions_remaining)} remaining
            </span>
          </div>
        </div>

        {/* Contribution history */}
        {historyToShow.length > 0 && (
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">
              Contribution History
            </div>
            <div className="space-y-1.5">
              {historyToShow.map((row) => (
                <div key={row.year} className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">{row.year}</span>
                  <span className="text-slate-200 font-medium">{formatCurrency(row.amount)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
