import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sankey, Tooltip, ResponsiveContainer, Layer, Rectangle } from 'recharts'
import { api } from '../../api/client'
import { formatCurrency } from '../../utils/format'

function useDailySpending(months = 6) {
  return useQuery({
    queryKey: ['spending', 'daily', months],
    queryFn: () => api.getDailySpending(months),
    staleTime: 30 * 60 * 1000,
  })
}

function useMoneyFlow(month: string) {
  return useQuery({
    queryKey: ['spending', 'flow', month],
    queryFn: () => api.getMoneyFlow(month),
    staleTime: 30 * 60 * 1000,
  })
}

function useStreaks() {
  return useQuery({
    queryKey: ['spending', 'streaks'],
    queryFn: api.getStreaks,
    staleTime: 30 * 60 * 1000,
  })
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

// ---------------------------------------------------------------------------
// Heatmap calendar — GitHub-contribution style
// ---------------------------------------------------------------------------

const HEAT_COLORS = ['bg-slate-700/40', 'bg-sky-900', 'bg-sky-700', 'bg-sky-500', 'bg-sky-300']
const DAY_LABELS = ['', 'Mon', '', 'Wed', '', 'Fri', '']

export function SpendingHeatmap() {
  const { data, isLoading } = useDailySpending(6)

  const grid = useMemo(() => {
    if (!data) return null
    const byDate = new Map(data.days.map((d) => [d.date, d]))

    // Build weeks (columns) from the Sunday on/before start to today
    const start = new Date(`${data.start}T00:00:00`)
    start.setDate(start.getDate() - start.getDay())
    const today = new Date()
    const weeks: { date: string; total: number; inRange: boolean }[][] = []
    const cursor = new Date(start)
    while (cursor <= today) {
      const week: { date: string; total: number; inRange: boolean }[] = []
      for (let i = 0; i < 7; i++) {
        const iso = cursor.toISOString().slice(0, 10)
        week.push({
          date: iso,
          total: byDate.get(iso)?.total ?? 0,
          inRange: cursor <= today,
        })
        cursor.setDate(cursor.getDate() + 1)
      }
      weeks.push(week)
    }

    // Intensity thresholds from non-zero quartiles
    const nonzero = data.days.map((d) => d.total).filter((t) => t > 0).sort((a, b) => a - b)
    const q = (p: number) => nonzero[Math.min(nonzero.length - 1, Math.floor(p * nonzero.length))] ?? 0
    const thresholds = [q(0.25), q(0.5), q(0.75)]

    const level = (total: number) => {
      if (total <= 0) return 0
      if (total <= thresholds[0]) return 1
      if (total <= thresholds[1]) return 2
      if (total <= thresholds[2]) return 3
      return 4
    }
    return { weeks, level }
  }, [data])

  if (isLoading) return <Skeleton className="h-40" />
  if (!data || !grid || data.days.length === 0) return null

  // Month labels above columns where the month changes
  const monthLabels = grid.weeks.map((week, i) => {
    const first = new Date(`${week[0].date}T00:00:00`)
    const prev = i > 0 ? new Date(`${grid.weeks[i - 1][0].date}T00:00:00`) : null
    return !prev || first.getMonth() !== prev.getMonth()
      ? first.toLocaleDateString('en-US', { month: 'short' })
      : ''
  })

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-1">Spending Heatmap</h3>
      <p className="text-xs text-slate-500 mb-4">Daily discretionary spend, last 6 months. Darker is heavier.</p>
      <div className="overflow-x-auto">
        <div className="inline-block">
          <div className="flex gap-[3px] mb-1 ml-8">
            {monthLabels.map((m, i) => (
              <div key={i} className="w-[13px] text-[9px] text-slate-500 overflow-visible whitespace-nowrap">{m}</div>
            ))}
          </div>
          <div className="flex gap-1">
            <div className="flex flex-col gap-[3px] w-7">
              {DAY_LABELS.map((d, i) => (
                <div key={i} className="h-[13px] text-[9px] text-slate-500 leading-[13px]">{d}</div>
              ))}
            </div>
            <div className="flex gap-[3px]">
              {grid.weeks.map((week, wi) => (
                <div key={wi} className="flex flex-col gap-[3px]">
                  {week.map((day) => (
                    <div
                      key={day.date}
                      title={`${day.date}: ${formatCurrency(day.total)}`}
                      className={`w-[13px] h-[13px] rounded-[3px] ${day.inRange ? HEAT_COLORS[grid.level(day.total)] : 'bg-transparent'}`}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-1.5 mt-2 ml-8 text-[10px] text-slate-500">
            <span>less</span>
            {HEAT_COLORS.map((c, i) => <div key={i} className={`w-[11px] h-[11px] rounded-[3px] ${c}`} />)}
            <span>more</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Money flow Sankey
// ---------------------------------------------------------------------------

const FLOW_COLORS = ['#38bdf8', '#34d399', '#f59e0b', '#a78bfa', '#fb7185', '#22d3ee', '#facc15', '#94a3b8', '#4ade80', '#64748b']

function SankeyNode(props: any) {
  const { x, y, width, height, index, payload } = props
  const isSource = index === 0
  return (
    <Layer key={`node-${index}`}>
      <Rectangle x={x} y={y} width={width} height={height} fill={FLOW_COLORS[index % FLOW_COLORS.length]} fillOpacity={0.9} radius={2} />
      <text
        x={isSource ? x - 6 : x + width + 6}
        y={y + height / 2}
        textAnchor={isSource ? 'end' : 'start'}
        dominantBaseline="middle"
        fontSize={11}
        fill="#cbd5e1"
      >
        {payload.name}
      </text>
    </Layer>
  )
}

export function MoneyFlowSankey({ month }: { month: string }) {
  const { data, isLoading } = useMoneyFlow(month)

  if (isLoading) return <Skeleton className="h-72" />
  if (!data || data.links.length === 0) return null

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-slate-300">Money Flow</h3>
        <span className="text-xs text-slate-500">
          {data.income > 0 ? `${formatCurrency(data.income)} in · ` : ''}{formatCurrency(data.outflows)} out
        </span>
      </div>
      <p className="text-xs text-slate-500 mb-3">Where the month's money went.</p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <Sankey
            data={{ nodes: data.nodes, links: data.links }}
            node={<SankeyNode />}
            nodePadding={24}
            margin={{ top: 10, right: 130, bottom: 10, left: 110 }}
            link={{ stroke: '#475569', strokeOpacity: 0.35 }}
          >
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
              formatter={(v: number) => formatCurrency(v)}
            />
          </Sankey>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Streaks
// ---------------------------------------------------------------------------

export function StreaksCard() {
  const { data, isLoading } = useStreaks()

  if (isLoading) return <Skeleton className="h-28" />
  if (!data) return null

  const items = [
    {
      label: data.has_budgets ? 'Days under budget' : 'No-spend streak',
      value: data.current_under_budget_streak,
      sub: `best in 90d: ${data.longest_streak_90d}`,
      fire: data.current_under_budget_streak >= 3,
    },
    {
      label: 'No-spend days this month',
      value: data.no_spend_days_this_month,
      sub: `${data.no_spend_days_90d} in the last 90 days`,
      fire: false,
    },
  ]

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Streaks</h3>
      <div className="grid grid-cols-2 gap-4">
        {items.map((it) => (
          <div key={it.label}>
            <div className="text-2xl font-bold text-slate-100">
              {it.value}{it.fire && ' 🔥'}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">{it.label}</div>
            <div className="text-[11px] text-slate-600">{it.sub}</div>
          </div>
        ))}
      </div>
      {data.has_budgets && (
        <p className="text-[11px] text-slate-600 mt-3">
          A day counts when discretionary spend stays under {formatCurrency(data.daily_budget)} (your budgets ÷ days in month).
        </p>
      )}
    </div>
  )
}
