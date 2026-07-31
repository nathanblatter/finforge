import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { formatCurrencyCompact, formatDate } from '../../utils/format'
import type { RunwaySeriesPoint } from '../../types'

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const point: RunwaySeriesPoint | undefined = payload[0]?.payload
  if (!point) return null
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 shadow-lg">
      <p className="text-xs text-slate-400 mb-1">{formatDate(label)}</p>
      <p className="text-xs font-medium text-sky-400">Projected: {formatCurrencyCompact(point.balance)}</p>
      <p className="text-xs text-slate-500">Range: {formatCurrencyCompact(point.low)} – {formatCurrencyCompact(point.high)}</p>
    </div>
  )
}

export default function RunwayChart({
  series,
  floorAmount,
  days,
}: {
  series: RunwaySeriesPoint[]
  floorAmount: number
  days: number
}) {
  const formatXAxis = (d: string) => {
    const dt = new Date(d + 'T00:00:00')
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={series} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="grad-runway-band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={formatXAxis}
          tick={{ fill: '#94a3b8', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          minTickGap={days > 60 ? 28 : 16}
        />
        <YAxis
          tickFormatter={(v: number) => formatCurrencyCompact(v)}
          tick={{ fill: '#94a3b8', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={64}
        />
        <Tooltip content={<CustomTooltip />} />
        {/* Confidence band: high bound as the top of the fill, low bound drawn beneath it */}
        <Area
          type="monotone"
          dataKey="high"
          stroke="none"
          fill="url(#grad-runway-band)"
          activeDot={false}
          isAnimationActive={false}
        />
        {/* Masks the area below "low" back to the card background (slate-800)
            so only the low→high band reads as shaded. */}
        <Area
          type="monotone"
          dataKey="low"
          stroke="none"
          fill="#1e293b"
          fillOpacity={1}
          activeDot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="balance"
          name="Projected balance"
          stroke="#0ea5e9"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
        />
        <ReferenceLine
          y={floorAmount}
          stroke="#f87171"
          strokeDasharray="4 4"
          strokeWidth={1.5}
          label={{ value: `Floor ${formatCurrencyCompact(floorAmount)}`, fill: '#f87171', fontSize: 11, position: 'insideTopLeft' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
