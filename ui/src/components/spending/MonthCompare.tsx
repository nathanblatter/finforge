import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { formatCurrency } from '../../utils/format'
import type { MonthlySpendingResponse } from '../../types'

function monthOptions(count = 12): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = []
  const now = new Date()
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    out.push({
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
    })
  }
  return out
}

function useMonth(month: string) {
  return useQuery({
    queryKey: ['spending', 'monthly', month],
    queryFn: () => api.getMonthlySpending(month),
    staleTime: 30 * 60 * 1000,
  })
}

function MonthPicker({ value, onChange, opts }: { value: string; onChange: (v: string) => void; opts: { label: string; value: string }[] }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-slate-900 border border-slate-600 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
    >
      {opts.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
    </select>
  )
}

export default function MonthCompare() {
  const opts = useMemo(() => monthOptions(12), [])
  const [aMonth, setAMonth] = useState(opts[1]?.value ?? opts[0].value) // previous month
  const [bMonth, setBMonth] = useState(opts[0].value) // current month

  const a = useMonth(aMonth)
  const b = useMonth(bMonth)

  const rows = useMemo(() => {
    const map = new Map<string, { a: number; b: number }>()
    const add = (resp: MonthlySpendingResponse | undefined, key: 'a' | 'b') => {
      resp?.by_category.forEach((c) => {
        const e = map.get(c.category) ?? { a: 0, b: 0 }
        e[key] = c.amount
        map.set(c.category, e)
      })
    }
    add(a.data, 'a')
    add(b.data, 'b')
    return Array.from(map.entries())
      .map(([category, v]) => ({ category, a: v.a, b: v.b, delta: v.b - v.a }))
      .sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))
  }, [a.data, b.data])

  const totalA = a.data?.total_discretionary ?? 0
  const totalB = b.data?.total_discretionary ?? 0
  const totalDelta = totalB - totalA
  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.delta)))

  const aLabel = opts.find((o) => o.value === aMonth)?.label ?? aMonth
  const bLabel = opts.find((o) => o.value === bMonth)?.label ?? bMonth

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-1">
        <h3 className="text-sm font-semibold text-slate-300">Compare Months</h3>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <MonthPicker value={aMonth} onChange={setAMonth} opts={opts} />
          <span>vs</span>
          <MonthPicker value={bMonth} onChange={setBMonth} opts={opts} />
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Discretionary by category. Bars point right (more) in rose, left (less) in emerald.
      </p>

      <div className="flex items-center justify-between mb-4 text-sm">
        <div>
          <span className="text-slate-500 text-xs">{aLabel}</span>
          <div className="text-slate-200 font-semibold">{formatCurrency(totalA)}</div>
        </div>
        <div className={`text-center font-semibold ${totalDelta > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
          {totalDelta > 0 ? '+' : ''}{formatCurrency(totalDelta)}
          <div className="text-[11px] text-slate-500 font-normal">net change</div>
        </div>
        <div className="text-right">
          <span className="text-slate-500 text-xs">{bLabel}</span>
          <div className="text-slate-200 font-semibold">{formatCurrency(totalB)}</div>
        </div>
      </div>

      {a.isLoading || b.isLoading ? (
        <div className="bg-slate-700 animate-pulse rounded-xl h-40" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-slate-500 py-6 text-center">No category data for these months.</p>
      ) : (
        <div className="space-y-1.5">
          {rows.map((r) => {
            const pct = (Math.abs(r.delta) / maxAbs) * 50 // half-width max
            const up = r.delta > 0
            return (
              <div key={r.category} className="flex items-center gap-2 text-sm">
                <div className="w-28 truncate text-slate-300 text-xs shrink-0">{r.category}</div>
                <div className="flex-1 flex items-center">
                  <div className="w-1/2 flex justify-end">
                    {!up && r.delta !== 0 && (
                      <div className="h-3 bg-emerald-500/70 rounded-l" style={{ width: `${pct}%` }} />
                    )}
                  </div>
                  <div className="w-px h-4 bg-slate-600" />
                  <div className="w-1/2 flex justify-start">
                    {up && (
                      <div className="h-3 bg-rose-500/70 rounded-r" style={{ width: `${pct}%` }} />
                    )}
                  </div>
                </div>
                <div className={`w-20 text-right tabular-nums text-xs shrink-0 ${
                  r.delta === 0 ? 'text-slate-600' : up ? 'text-rose-400' : 'text-emerald-400'
                }`}>
                  {r.delta > 0 ? '+' : ''}{formatCurrency(r.delta)}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
