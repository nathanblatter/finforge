import type { AccountBalance } from '../../types'
import { formatCurrency, formatDate } from '../../utils/format'

const DISPLAY_ORDER = [
  'WF Checking', 'WF Credit Card', 'Amex Credit Card', 'Schwab Brokerage', 'Schwab Roth IRA',
]

function sortKey(alias: string) {
  const idx = DISPLAY_ORDER.indexOf(alias)
  return idx === -1 ? DISPLAY_ORDER.length : idx
}

// PRD: Roth IRA is account_type === 'ira' — visually distinct, muted, locked
function isIRA(b: AccountBalance) {
  return b.account_type === 'ira'
}

function LockIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="text-slate-500 flex-shrink-0">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

function TypeBadge({ type }: { type: string }) {
  const label = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return (
    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-700 text-slate-400 uppercase tracking-wider">
      {label}
    </span>
  )
}

function AccountCard({ b }: { b: AccountBalance }) {
  const ira = isIRA(b)
  return (
    <div className={[
      'rounded-xl p-4 flex flex-col gap-2',
      ira
        ? 'bg-slate-800/50 border border-slate-600 opacity-75'
        : 'bg-slate-800 border border-slate-700',
    ].join(' ')}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-1.5">
            {ira && <LockIcon />}
            <span className="text-sm font-semibold text-slate-100 truncate">{b.alias}</span>
          </div>
          {/* PRD: Roth IRA card must show "Retirement — Long-term" label */}
          {ira && <span className="text-xs text-slate-500">Retirement — Long-term</span>}
          <span className="text-xs text-slate-400">{b.institution}</span>
        </div>
        <TypeBadge type={b.account_type} />
      </div>

      <span className={`text-xl font-bold ${ira ? 'text-slate-400' : 'text-slate-100'}`}>
        {formatCurrency(b.balance_amount)}
      </span>

      <div className="flex items-center pt-1 border-t border-slate-700/50 mt-auto">
        <span className="text-[11px] text-slate-500">Updated {formatDate(b.last_updated)}</span>
      </div>
    </div>
  )
}

export default function AccountCards({ balances }: { balances: AccountBalance[] }) {
  const sorted = [...balances].sort((a, b) => sortKey(a.alias) - sortKey(b.alias))
  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-100 mb-3">Accounts</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {sorted.map(b => <AccountCard key={b.alias} b={b} />)}
      </div>
    </div>
  )
}
