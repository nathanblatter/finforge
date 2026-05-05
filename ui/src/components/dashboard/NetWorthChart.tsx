import { useState, useMemo } from 'react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { formatCurrencyCompact } from '../../utils/format'

const API_KEY = import.meta.env.VITE_API_KEY as string
const TOKEN_KEY = 'finforge_token'

interface TrendPoint {
  date: string
  net_worth: number
  [key: string]: string | number
}

const RANGE_OPTIONS = [
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '1Y', days: 365 },
  { label: 'All', days: 730 },
]

const LINE_COLORS: Record<string, string> = {
  net_worth: '#0ea5e9',
  'WF Checking': '#34d399',
  'WF Credit Card': '#f87171',
  'Amex Credit Card': '#fb923c',
  'Schwab Brokerage': '#818cf8',
  'Schwab Roth IRA': '#a78bfa',
}

async function fetchTrend(days: number): Promise<TrendPoint[]> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = { 'X-API-Key': API_KEY }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`/api/v1/balances/trend?days=${days}`, { headers })
  if (!res.ok) throw new Error('Failed to fetch trend')
  return res.json()
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="text-xs font-medium" style={{ color: p.stroke }}>
          {p.name}: {formatCurrencyCompact(p.value)}
        </p>
      ))}
    </div>
  )
}

export default function NetWorthChart() {
  const [days, setDays] = useState(365)
  const [visibleLines, setVisibleLines] = useState<Set<string>>(new Set(['net_worth']))

  const { data: rawData, isLoading } = useQuery({
    queryKey: ['balance-trend', days],
    queryFn: () => fetchTrend(days),
  })

  // Discover all available series from the data
  const availableSeries = useMemo(() => {
    if (!rawData?.length) return ['net_worth']
    const keys = new Set<string>()
    rawData.forEach(pt => {
      Object.keys(pt).forEach(k => {
        if (k !== 'date') keys.add(k)
      })
    })
    // net_worth first, then alphabetical
    const sorted = Array.from(keys).filter(k => k !== 'net_worth').sort()
    return ['net_worth', ...sorted]
  }, [rawData])

  function toggleLine(key: string) {
    setVisibleLines(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        if (next.size > 1) next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const formatDate = (d: string) => {
    const dt = new Date(d + 'T00:00:00')
    if (days <= 30) return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    return dt.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Net Worth Trend</h2>
          <p className="text-xs text-slate-500 mt-0.5">Balance history over time</p>
        </div>
        <div className="flex gap-1">
          {RANGE_OPTIONS.map(opt => (
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

      {/* Series toggles */}
      <div className="flex flex-wrap gap-2 mb-3">
        {availableSeries.map(key => (
          <button
            key={key}
            onClick={() => toggleLine(key)}
            className={`flex items-center gap-1.5 px-2 py-0.5 text-xs rounded-full transition-colors ${
              visibleLines.has(key)
                ? 'bg-slate-700 text-slate-200'
                : 'bg-slate-900 text-slate-500'
            }`}
          >
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: visibleLines.has(key) ? (LINE_COLORS[key] || '#64748b') : '#334155' }}
            />
            {key === 'net_worth' ? 'Net Worth' : key}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48 rounded-lg bg-slate-900/50">
          <p className="text-sm text-slate-400">Loading trend data...</p>
        </div>
      ) : !rawData?.length ? (
        <div className="flex items-center justify-center h-48 rounded-lg bg-slate-900/50">
          <div className="text-center">
            <p className="text-sm text-slate-400">Not enough data yet</p>
            <p className="text-xs text-slate-600 mt-1">Trend builds as daily syncs run</p>
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={rawData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              {availableSeries.map(key => (
                <linearGradient key={key} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={LINE_COLORS[key] || '#64748b'} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={LINE_COLORS[key] || '#64748b'} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tickFormatter={(v: number) => formatCurrencyCompact(v)}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={64}
            />
            <Tooltip content={<CustomTooltip />} />
            {availableSeries.filter(k => visibleLines.has(k)).map(key => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                name={key === 'net_worth' ? 'Net Worth' : key}
                stroke={LINE_COLORS[key] || '#64748b'}
                fill={`url(#grad-${key})`}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
