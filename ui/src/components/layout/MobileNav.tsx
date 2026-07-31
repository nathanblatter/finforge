import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAlerts } from '../../hooks/useAlerts'

const primary = [
  { label: 'Home', to: '/' },
  { label: 'Spending', to: '/spending' },
  { label: 'Portfolio', to: '/portfolio' },
  { label: 'Alerts', to: '/alerts' },
]

const more = [
  { label: 'Budgets', to: '/budgets' },
  { label: 'Subscriptions', to: '/subscriptions' },
  { label: 'Reimburse', to: '/reimbursement' },
  { label: 'Reports', to: '/reports' },
  { label: 'Investments', to: '/investments' },
  { label: 'Tax Center', to: '/tax' },
  { label: 'Watchlists', to: '/watchlists' },
  { label: 'Goals', to: '/goals' },
  { label: 'Chat', to: '/chat' },
  { label: 'Insights', to: '/insights' },
  { label: 'Health Score', to: '/health-score' },
  { label: 'Settings', to: '/settings' },
]

const ICONS: Record<string, JSX.Element> = {
  Home: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  Spending: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2" /><line x1="1" y1="10" x2="23" y2="10" />
    </svg>
  ),
  Portfolio: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  ),
  Alerts: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  ),
}

export default function MobileNav() {
  const [moreOpen, setMoreOpen] = useState(false)
  const { data: alertsData } = useAlerts()
  const unacknowledgedCount = alertsData?.unacknowledged_count ?? 0

  return (
    <>
      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-40 bg-slate-950/70" onClick={() => setMoreOpen(false)}>
          <div
            className="absolute bottom-16 inset-x-3 bg-slate-800 border border-slate-700 rounded-xl p-3 grid grid-cols-2 gap-1"
            onClick={(e) => e.stopPropagation()}
          >
            {more.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMoreOpen(false)}
                className={({ isActive }) =>
                  `px-3 py-2.5 rounded-lg text-sm font-medium ${
                    isActive ? 'bg-slate-700 text-sky-400' : 'text-slate-300'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      )}

      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-slate-900/95 backdrop-blur border-t border-slate-700 flex items-stretch pb-[env(safe-area-inset-bottom)]">
        {primary.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={() => setMoreOpen(false)}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium relative ${
                isActive ? 'text-sky-400' : 'text-slate-500'
              }`
            }
          >
            {ICONS[item.label]}
            {item.label}
            {item.label === 'Alerts' && unacknowledgedCount > 0 && (
              <span className="absolute top-1 right-[calc(50%-18px)] min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-rose-500 text-white text-[9px] font-bold leading-none">
                {unacknowledgedCount > 99 ? '99+' : unacknowledgedCount}
              </span>
            )}
          </NavLink>
        ))}
        <button
          onClick={() => setMoreOpen((v) => !v)}
          className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium ${
            moreOpen ? 'text-sky-400' : 'text-slate-500'
          }`}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /><circle cx="5" cy="12" r="1" />
          </svg>
          More
        </button>
      </nav>
    </>
  )
}
