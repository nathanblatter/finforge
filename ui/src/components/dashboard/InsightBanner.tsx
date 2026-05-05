import type { Insight } from '../../types'
import { formatDate } from '../../utils/format'

function TypeBadge({ type }: { type: string }) {
  const label = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return (
    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-400 border border-sky-500/30 uppercase tracking-wider">
      {label}
    </span>
  )
}

export default function InsightBanner({ insight }: { insight?: Insight }) {
  if (!insight) return null
  return (
    <div className="bg-slate-800/60 border border-sky-500/30 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <span className="text-sky-400 mt-0.5 flex-shrink-0">✦</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-sky-400 uppercase tracking-wider">AI Insight</span>
            <TypeBadge type={insight.insight_type} />
          </div>
          <p className="text-sm text-slate-200 leading-relaxed">{insight.content}</p>
        </div>
        <span className="text-[11px] text-slate-500 flex-shrink-0 whitespace-nowrap">
          {formatDate(insight.insight_date)}
        </span>
      </div>
    </div>
  )
}
