import { useEffect, useMemo, useState } from 'react'
import Header from '../components/layout/Header'
import { useToast } from '../components/Toast'
import {
  useTrips, useTrip, useCreateTrip, useUpdateTrip, useDeleteTrip,
  useSetTripTransaction, useTripCandidates,
} from '../hooks/useTrips'
import { formatCurrency, formatCurrencyCompact, formatDate } from '../utils/format'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { Trip, TripDetailResponse, TripListItem, TripTransaction } from '../types'

function Panel({ title, sub, children, actions }: {
  title: string; sub?: string; children: React.ReactNode; actions?: React.ReactNode
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-start justify-between mb-1">
        <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
        {actions}
      </div>
      {sub && <p className="text-xs text-slate-500 mb-4">{sub}</p>}
      {children}
    </div>
  )
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

function Stat({ label, value, tone = 'text-slate-100', sub }: {
  label: string; value: string; tone?: string; sub?: string
}) {
  return (
    <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-bold ${tone}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

const STATUS_STYLE: Record<Trip['status'], string> = {
  upcoming: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  completed: 'bg-slate-700 text-slate-400 border-slate-600',
}

function StatusChip({ status }: { status: Trip['status'] }) {
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${STATUS_STYLE[status]}`}>
      {status}
    </span>
  )
}

function BudgetBar({ spend, budget }: { spend: number; budget: number | null }) {
  if (budget == null || budget <= 0) return null
  const pct = Math.min(100, (spend / budget) * 100)
  const over = spend > budget
  return (
    <div>
      <div className="h-2 bg-slate-900 rounded-full overflow-hidden border border-slate-700">
        <div
          className={`h-full rounded-full transition-all ${over ? 'bg-rose-500' : pct > 85 ? 'bg-amber-500' : 'bg-emerald-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between mt-1 text-[11px] text-slate-500">
        <span>{formatCurrencyCompact(spend)} spent</span>
        <span className={over ? 'text-rose-400 font-semibold' : ''}>
          {over ? `${formatCurrencyCompact(spend - budget)} over` : `${formatCurrencyCompact(budget - spend)} left`} of {formatCurrencyCompact(budget)}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create / edit form
// ---------------------------------------------------------------------------

function TripForm({ trip, onClose }: { trip: Trip | null; onClose: () => void }) {
  const create = useCreateTrip()
  const update = useUpdateTrip()
  const toast = useToast()

  const [name, setName] = useState(trip?.name ?? '')
  const [destination, setDestination] = useState(trip?.destination ?? '')
  const [startDate, setStartDate] = useState(trip?.start_date ?? '')
  const [endDate, setEndDate] = useState(trip?.end_date ?? '')
  const [budget, setBudget] = useState(trip?.budget != null ? String(trip.budget) : '')
  const [notes, setNotes] = useState(trip?.notes ?? '')

  const pending = create.isPending || update.isPending
  const valid = name.trim() && startDate && endDate && endDate >= startDate

  const save = () => {
    if (!valid) return
    const onError = (e: any) => toast.error(e?.message ?? 'Could not save trip')
    if (trip) {
      update.mutate(
        {
          id: trip.id,
          body: {
            name: name.trim(),
            destination: destination.trim() || undefined,
            start_date: startDate,
            end_date: endDate,
            budget: budget ? parseFloat(budget) : undefined,
            clear_budget: !budget,
            notes,
          },
        },
        { onSuccess: () => { toast.success('Trip updated'); onClose() }, onError },
      )
    } else {
      create.mutate(
        {
          name: name.trim(),
          destination: destination.trim() || undefined,
          start_date: startDate,
          end_date: endDate,
          budget: budget ? parseFloat(budget) : undefined,
          notes: notes || undefined,
        },
        { onSuccess: () => { toast.success('Trip created'); onClose() }, onError },
      )
    }
  }

  const inputCls = 'w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500'

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-slate-800 border border-slate-700 rounded-xl p-5 w-full max-w-md space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-slate-200">{trip ? 'Edit Trip' : 'New Trip'}</h3>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Trip name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Tokyo 2026" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Destination</label>
          <input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="e.g. Tokyo, Japan" className={inputCls} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Start date *</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">End date *</label>
            <input type="date" value={endDate} min={startDate || undefined} onChange={(e) => setEndDate(e.target.value)} className={inputCls} />
          </div>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Budget ($)</label>
          <input type="number" min="0" step="100" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="optional" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={inputCls} />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!valid || pending}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {pending ? 'Saving...' : trip ? 'Save Changes' : 'Create Trip'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Trip cards
// ---------------------------------------------------------------------------

function TripCard({ trip, selected, onSelect }: {
  trip: TripListItem; selected: boolean; onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      className={`text-left bg-slate-800 border rounded-xl p-4 w-full transition-colors ${
        selected ? 'border-sky-500' : 'border-slate-700 hover:border-slate-600'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-sm font-semibold text-slate-100 truncate">{trip.name}</span>
        <StatusChip status={trip.status} />
      </div>
      <div className="text-xs text-slate-500 mb-2">
        {trip.destination ? `${trip.destination} · ` : ''}{formatDate(trip.start_date)} – {formatDate(trip.end_date)}
      </div>
      <div className="text-lg font-bold text-slate-100 mb-2">
        {formatCurrency(trip.total_spend)}
        <span className="text-xs font-normal text-slate-500 ml-2">{trip.transaction_count} transactions</span>
      </div>
      <BudgetBar spend={trip.total_spend} budget={trip.budget} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

const TOOLTIP_STYLE = {
  backgroundColor: '#1e293b',
  border: '1px solid #334155',
  borderRadius: 8,
  fontSize: 12,
}

function DailySpendChart({ detail }: { detail: TripDetailResponse }) {
  const data = useMemo(() => {
    let running = 0
    return detail.summary.by_day.map((d) => {
      running += d.amount
      return { date: d.date, daily: d.amount, cumulative: Math.round(running * 100) / 100 }
    })
  }, [detail])

  if (data.length === 0) {
    return <p className="text-sm text-slate-500">No transactions yet — spending inside the trip window shows up here automatically.</p>
  }

  const budget = detail.summary.budget
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d).replace(/, \d{4}$/, '')} tick={{ fill: '#64748b', fontSize: 11 }} />
        <YAxis tickFormatter={(v: number) => formatCurrencyCompact(v)} tick={{ fill: '#64748b', fontSize: 11 }} width={70} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(d) => formatDate(String(d))}
          formatter={(value: number, key: string) => [formatCurrency(value), key === 'daily' ? 'Spent that day' : 'Cumulative']}
        />
        {budget != null && budget > 0 && (
          <ReferenceLine y={budget} stroke="#f43f5e" strokeDasharray="6 4" label={{ value: 'Budget', fill: '#f43f5e', fontSize: 11, position: 'insideTopRight' }} />
        )}
        <Bar dataKey="daily" fill="#0ea5e9" radius={[3, 3, 0, 0]} maxBarSize={28} />
        <Line dataKey="cumulative" stroke="#f59e0b" strokeWidth={2} dot={false} type="monotone" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function CategoryBreakdown({ detail }: { detail: TripDetailResponse }) {
  const cats = detail.summary.by_category
  if (cats.length === 0) return <p className="text-sm text-slate-500">Nothing categorized yet.</p>
  const max = Math.max(...cats.map((c) => c.amount), 1)
  return (
    <div className="space-y-2.5">
      {cats.map((c) => (
        <div key={c.category}>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-slate-300">{c.category} <span className="text-slate-600">×{c.count}</span></span>
            <span className="text-slate-400 font-medium">{formatCurrency(c.amount)}</span>
          </div>
          <div className="h-2 bg-slate-900 rounded-full overflow-hidden">
            <div className="h-full bg-sky-500/80 rounded-full" style={{ width: `${Math.max(2, (c.amount / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Transactions list + candidate search
// ---------------------------------------------------------------------------

function TransactionRow({ txn, action, actionLabel, actionTone }: {
  txn: TripTransaction; action: () => void; actionLabel: string; actionTone: string
}) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-slate-700/60 last:border-0">
      <div className="w-20 shrink-0 text-xs text-slate-500">{formatDate(txn.date)}</div>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-200 truncate">
          {txn.merchant_name ?? 'Unknown merchant'}
          {txn.is_pending && <span className="ml-2 text-[10px] text-amber-400">pending</span>}
          {txn.source === 'manual' && <span className="ml-2 text-[10px] text-sky-400">added</span>}
        </div>
        <div className="text-[11px] text-slate-500 truncate">
          {txn.category ?? 'Uncategorized'} · {txn.account_alias}
        </div>
      </div>
      <div className={`text-sm font-medium shrink-0 ${txn.amount < 0 ? 'text-emerald-400' : 'text-slate-100'}`}>
        {formatCurrency(txn.amount)}
      </div>
      <button onClick={action} className={`shrink-0 text-xs font-medium px-2 py-1 rounded transition-colors ${actionTone}`}>
        {actionLabel}
      </button>
    </div>
  )
}

function TripTransactions({ detail }: { detail: TripDetailResponse }) {
  const setTxn = useSetTripTransaction()
  const toast = useToast()
  const [showAdd, setShowAdd] = useState(false)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300)
    return () => clearTimeout(t)
  }, [search])

  const candidates = useTripCandidates(detail.id, debounced, showAdd)

  const toggle = (transactionId: string, included: boolean) => {
    setTxn.mutate(
      { tripId: detail.id, transactionId, included },
      { onError: (e: any) => toast.error(e?.message ?? 'Could not update transaction') },
    )
  }

  return (
    <Panel
      title={`Transactions (${detail.transactions.length})`}
      sub="Pulled in automatically from the trip window. Exclude anything unrelated, or add pre-trip bookings like flights and hotels."
      actions={
        <button
          onClick={() => setShowAdd((v) => !v)}
          className="text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors"
        >
          {showAdd ? 'Done adding' : '+ Add transactions'}
        </button>
      }
    >
      {showAdd && (
        <div className="mb-4 bg-slate-900/60 border border-slate-700 rounded-lg p-3">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search merchants up to 6 months before the trip (e.g. United, Airbnb)..."
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500 mb-2"
          />
          <div className="max-h-64 overflow-y-auto">
            {candidates.isLoading && <p className="text-xs text-slate-500 py-2">Searching...</p>}
            {candidates.data?.candidates.length === 0 && (
              <p className="text-xs text-slate-500 py-2">No matching transactions found.</p>
            )}
            {candidates.data?.candidates.map((t) => (
              <TransactionRow
                key={t.id}
                txn={t}
                action={() => toggle(t.id, true)}
                actionLabel="Add"
                actionTone="text-emerald-400 hover:bg-emerald-500/10"
              />
            ))}
          </div>
        </div>
      )}

      {detail.transactions.length === 0 ? (
        <p className="text-sm text-slate-500">No transactions in this trip yet.</p>
      ) : (
        <div className="max-h-[28rem] overflow-y-auto">
          {detail.transactions.map((t) => (
            <TransactionRow
              key={t.id}
              txn={t}
              action={() => toggle(t.id, false)}
              actionLabel={t.source === 'manual' ? 'Remove' : 'Exclude'}
              actionTone="text-slate-500 hover:text-rose-400 hover:bg-rose-500/10"
            />
          ))}
        </div>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Detail
// ---------------------------------------------------------------------------

function TripDetail({ tripId, onEdit }: { tripId: string; onEdit: (trip: Trip) => void }) {
  const { data: detail, isLoading, error } = useTrip(tripId)
  const del = useDeleteTrip()
  const toast = useToast()

  if (isLoading) return <Skeleton className="h-96" />
  if (error || !detail) {
    return <Panel title="Trip"><p className="text-sm text-slate-500">{(error as any)?.message ?? 'Could not load trip.'}</p></Panel>
  }

  const s = detail.summary
  const remove = () => {
    if (!window.confirm(`Delete "${detail.name}"? The transactions themselves are untouched.`)) return
    del.mutate(detail.id, {
      onSuccess: () => toast.success('Trip deleted'),
      onError: (e: any) => toast.error(e?.message ?? 'Could not delete trip'),
    })
  }

  return (
    <div className="space-y-6">
      <Panel
        title={detail.destination ? `${detail.name} — ${detail.destination}` : detail.name}
        sub={`${formatDate(detail.start_date)} – ${formatDate(detail.end_date)} · ${s.trip_days} day${s.trip_days === 1 ? '' : 's'}${detail.notes ? ` · ${detail.notes}` : ''}`}
        actions={
          <div className="flex gap-3">
            <button onClick={() => onEdit(detail)} className="text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors">Edit</button>
            <button onClick={remove} className="text-xs font-medium text-slate-500 hover:text-rose-400 transition-colors">Delete</button>
          </div>
        }
      >
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <Stat label="Total Spend" value={formatCurrency(s.total_spend)} sub={s.pre_trip_spend !== 0 ? `${formatCurrency(s.pre_trip_spend)} booked pre-trip` : undefined} />
          <Stat
            label={s.budget != null ? 'Budget Remaining' : 'Budget'}
            value={s.budget_remaining != null ? formatCurrency(s.budget_remaining) : '—'}
            tone={s.budget_remaining != null && s.budget_remaining < 0 ? 'text-rose-400' : 'text-emerald-400'}
            sub={s.budget != null ? `of ${formatCurrency(s.budget)} (${s.budget_pct ?? 0}%)` : 'no budget set'}
          />
          <Stat
            label="Daily Average"
            value={s.daily_avg != null ? formatCurrency(s.daily_avg) : '—'}
            sub={detail.status === 'active' ? `day ${s.days_elapsed} of ${s.trip_days}` : `over ${s.trip_days} days`}
          />
          <Stat label="Transactions" value={String(s.transaction_count)} />
          {s.projected_total != null && (
            <Stat
              label="Projected Total"
              value={formatCurrency(s.projected_total)}
              tone={s.budget != null && s.projected_total > s.budget ? 'text-rose-400' : 'text-slate-100'}
              sub="at current daily run-rate"
            />
          )}
        </div>
        {s.budget != null && (
          <div className="mt-4">
            <BudgetBar spend={s.total_spend} budget={s.budget} />
          </div>
        )}
      </Panel>

      <div className="grid lg:grid-cols-2 gap-6">
        <Panel title="Spend Over Time" sub="Daily spend (bars), running total (line), budget (dashed).">
          <DailySpendChart detail={detail} />
        </Panel>
        <Panel title="Where It Went" sub="Net by category — refunds subtract.">
          <CategoryBreakdown detail={detail} />
        </Panel>
      </div>

      <TripTransactions detail={detail} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TripsPage() {
  const { data, isLoading } = useTrips()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [formTrip, setFormTrip] = useState<Trip | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const trips = data?.trips ?? []

  useEffect(() => {
    if (trips.length === 0) {
      setSelectedId(null)
    } else if (!selectedId || !trips.some((t) => t.id === selectedId)) {
      // Prefer the trip happening right now, else the most recent.
      const active = trips.find((t) => t.status === 'active')
      setSelectedId((active ?? trips[0]).id)
    }
  }, [trips, selectedId])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Header title="Trip Tracker" />
        <button
          onClick={() => { setFormTrip(null); setFormOpen(true) }}
          className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          + New Trip
        </button>
      </div>

      {isLoading ? (
        <Skeleton className="h-32" />
      ) : trips.length === 0 ? (
        <Panel title="No trips yet" sub="Create a trip with its dates and destination — every spending transaction inside the window is pulled in automatically.">
          <button
            onClick={() => { setFormTrip(null); setFormOpen(true) }}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Create your first trip
          </button>
        </Panel>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {trips.map((t) => (
            <TripCard key={t.id} trip={t} selected={t.id === selectedId} onSelect={() => setSelectedId(t.id)} />
          ))}
        </div>
      )}

      {selectedId && <TripDetail tripId={selectedId} onEdit={(t) => { setFormTrip(t); setFormOpen(true) }} />}

      {formOpen && <TripForm trip={formTrip} onClose={() => setFormOpen(false)} />}
    </div>
  )
}
