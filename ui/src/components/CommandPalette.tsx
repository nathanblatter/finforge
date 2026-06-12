import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { formatCurrency } from '../utils/format'

const PAGES = [
  { label: 'Dashboard', to: '/' },
  { label: 'Spending', to: '/spending' },
  { label: 'Budgets', to: '/budgets' },
  { label: 'Subscriptions', to: '/subscriptions' },
  { label: 'Reimburse', to: '/reimbursement' },
  { label: 'Reports', to: '/reports' },
  { label: 'Investments', to: '/investments' },
  { label: 'Portfolio', to: '/portfolio' },
  { label: 'Watchlists', to: '/watchlists' },
  { label: 'Goals', to: '/goals' },
  { label: 'Chat', to: '/chat' },
  { label: 'Insights', to: '/insights' },
  { label: 'Alerts', to: '/alerts' },
  { label: 'Settings', to: '/settings' },
]

interface Item {
  key: string
  section: 'Pages' | 'Merchants' | 'Transactions'
  label: string
  sub?: string
  right?: string
  to: string
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [active, setActive] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    const onOpen = () => setOpen(true)
    window.addEventListener('keydown', onKey)
    window.addEventListener('finforge:palette', onOpen)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('finforge:palette', onOpen)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setQ('')
      setDebounced('')
      setActive(0)
      // Focus after the panel renders
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 250)
    return () => clearTimeout(t)
  }, [q])

  const serverQ = debounced.trim()
  const { data, isFetching } = useQuery({
    queryKey: ['palette', serverQ],
    queryFn: () => api.searchSpending(serverQ),
    enabled: open && serverQ.length >= 2,
    staleTime: 60 * 1000,
    retry: false,
  })

  const items = useMemo<Item[]>(() => {
    const out: Item[] = []
    const needle = q.trim().toLowerCase()
    const pages = needle
      ? PAGES.filter((p) => p.label.toLowerCase().includes(needle))
      : PAGES.slice(0, 6)
    for (const p of pages) {
      out.push({ key: `page:${p.to}`, section: 'Pages', label: p.label, to: p.to })
    }
    if (serverQ.length >= 2 && data) {
      for (const m of data.merchants) {
        out.push({
          key: `merchant:${m.merchant}`,
          section: 'Merchants',
          label: m.merchant,
          sub: `${m.count}× in the last year`,
          right: formatCurrency(m.total),
          to: `/merchant?name=${encodeURIComponent(m.merchant)}`,
        })
      }
      for (const t of data.transactions) {
        out.push({
          key: `txn:${t.id}`,
          section: 'Transactions',
          label: t.merchant_name ?? 'Unknown',
          sub: `${t.date} · ${t.category ?? '—'} · ${t.account_alias}`,
          right: formatCurrency(Math.abs(t.amount)),
          to: t.merchant_name
            ? `/merchant?name=${encodeURIComponent(t.merchant_name)}`
            : '/spending',
        })
      }
    }
    return out
  }, [q, serverQ, data])

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(items.length - 1, 0)))
  }, [items.length])

  const select = (item: Item) => {
    setOpen(false)
    navigate(item.to)
  }

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === 'Enter' && items[active]) {
      e.preventDefault()
      select(items[active])
    }
  }

  if (!open) return null

  let lastSection: string | null = null

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-start justify-center pt-[15vh] px-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false)
      }}
    >
      <div className="w-full max-w-xl bg-slate-800 border border-slate-600 rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-4 border-b border-slate-700">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500 shrink-0">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search merchants, transactions, pages…"
            className="flex-1 bg-transparent py-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          {isFetching && <span className="text-xs text-slate-500">searching…</span>}
          <kbd className="text-[10px] text-slate-500 border border-slate-600 rounded px-1.5 py-0.5">esc</kbd>
        </div>

        <div className="max-h-[50vh] overflow-y-auto py-2">
          {items.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500 text-center">
              {serverQ.length >= 2 ? 'No matches.' : 'Type to search across FinForge.'}
            </p>
          ) : (
            items.map((item, i) => {
              const header = item.section !== lastSection ? item.section : null
              lastSection = item.section
              return (
                <div key={item.key}>
                  {header && (
                    <div className="px-4 pt-2 pb-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                      {header}
                    </div>
                  )}
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => select(item)}
                    className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      i === active ? 'bg-slate-700 text-slate-100' : 'text-slate-300'
                    }`}
                  >
                    <span className="flex-1 min-w-0">
                      <span className="block truncate">{item.label}</span>
                      {item.sub && <span className="block text-[11px] text-slate-500 truncate">{item.sub}</span>}
                    </span>
                    {item.right && <span className="text-xs text-slate-400 tabular-nums shrink-0">{item.right}</span>}
                  </button>
                </div>
              )
            })
          )}
        </div>

        <div className="px-4 py-2 border-t border-slate-700 text-[10px] text-slate-600 flex gap-4">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>merchants link to their history</span>
        </div>
      </div>
    </div>
  )
}
