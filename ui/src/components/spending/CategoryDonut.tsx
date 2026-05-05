import { useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Sector } from 'recharts'
import { formatCurrency, formatPct } from '../../utils/format'
import type { CategorySpend } from '../../types'

const COLORS = [
  '#38bdf8', '#818cf8', '#34d399', '#fb923c', '#f472b6',
  '#a78bfa', '#4ade80', '#fbbf24', '#60a5fa', '#f87171',
]

interface Props {
  data: CategorySpend[]
}

function renderActiveShape(props: Record<string, unknown>) {
  const {
    cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill,
  } = props as {
    cx: number; cy: number; innerRadius: number; outerRadius: number
    startAngle: number; endAngle: number; fill: string
  }
  return (
    <Sector
      cx={cx} cy={cy}
      innerRadius={innerRadius}
      outerRadius={(outerRadius as number) + 6}
      startAngle={startAngle}
      endAngle={endAngle}
      fill={fill}
    />
  )
}

export default function CategoryDonut({ data }: Props) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const sorted = [...data].sort((a, b) => b.amount - a.amount)

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Spending by Category</h3>
      <div className="flex flex-col lg:flex-row gap-6 items-center">
        <div className="w-full lg:w-64 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={sorted}
                dataKey="amount"
                nameKey="category"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                activeIndex={activeIndex ?? undefined}
                activeShape={renderActiveShape}
                onClick={(_, index) =>
                  setActiveIndex(activeIndex === index ? null : index)
                }
              >
                {sorted.map((_, i) => (
                  <Cell
                    key={i}
                    fill={COLORS[i % COLORS.length]}
                    opacity={activeIndex === null || activeIndex === i ? 1 : 0.4}
                    style={{ cursor: 'pointer' }}
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => formatCurrency(value)}
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                labelStyle={{ color: '#94a3b8' }}
                itemStyle={{ color: '#f1f5f9' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex-1 space-y-2 w-full">
          {sorted.map((cat, i) => (
            <div
              key={cat.category}
              className={`flex items-center justify-between text-sm cursor-pointer rounded px-2 py-1 transition-colors ${
                activeIndex === i ? 'bg-slate-700' : 'hover:bg-slate-750'
              }`}
              onClick={() => setActiveIndex(activeIndex === i ? null : i)}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ background: COLORS[i % COLORS.length] }}
                />
                <span className="text-slate-300 truncate">{cat.category}</span>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0 ml-2">
                <span className="text-slate-400 text-xs">{formatPct(cat.pct_of_total)}</span>
                <span className="text-slate-100 font-medium">{formatCurrency(cat.amount)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
