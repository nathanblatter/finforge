interface MetricCardProps {
  label: string
  value: string
  subtitle?: string
  trend?: 'up' | 'down' | 'neutral'
  accentColor?: string
}

function TrendArrow({ trend }: { trend: 'up' | 'down' | 'neutral' }) {
  if (trend === 'up') {
    return (
      <span className="inline-flex items-center text-emerald-400 text-sm font-medium">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="mr-0.5">
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
        Up
      </span>
    )
  }
  if (trend === 'down') {
    return (
      <span className="inline-flex items-center text-rose-400 text-sm font-medium">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="mr-0.5">
          <line x1="12" y1="5" x2="12" y2="19" />
          <polyline points="19 12 12 19 5 12" />
        </svg>
        Down
      </span>
    )
  }
  return (
    <span className="inline-flex items-center text-slate-400 text-sm font-medium">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="mr-0.5">
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
      Neutral
    </span>
  )
}

export default function MetricCard({
  label, value, subtitle, trend, accentColor = 'text-sky-400',
}: MetricCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 flex flex-col gap-1.5">
      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold ${accentColor} leading-tight`}>{value}</span>
      <div className="flex items-center justify-between mt-0.5 gap-2 min-h-[20px]">
        {subtitle && <span className="text-xs text-slate-500 truncate">{subtitle}</span>}
        {trend && <TrendArrow trend={trend} />}
      </div>
    </div>
  )
}
