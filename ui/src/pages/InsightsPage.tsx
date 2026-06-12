import Header from '../components/layout/Header'
import { useInsightsHistory } from '../hooks/useInsights'
import { formatDate } from '../utils/format'

function TypeBadge({ type }: { type: string }) {
  const label = type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-500/20 text-sky-400 border border-sky-500/30 uppercase tracking-wider">
      {label}
    </span>
  )
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function InsightsPage() {
  const { data, isLoading } = useInsightsHistory(50)
  const insights = data?.insights ?? []
  const now = Date.now()

  return (
    <div className="space-y-6 max-w-[800px]">
      <Header title="AI Insights" />
      <p className="text-sm text-slate-500 -mt-2">
        Claude-generated insights from your daily financial analysis, newest first.
      </p>

      {isLoading ? (
        <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : insights.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <p className="text-slate-400 text-sm">No insights yet.</p>
          <p className="text-slate-500 text-xs mt-1">Insights are generated nightly by the Claude engine.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {insights.map((ins) => {
            const expired = new Date(ins.expires_at).getTime() < now
            return (
              <div
                key={ins.id}
                className={`bg-slate-800/60 border rounded-xl p-4 ${expired ? 'border-slate-700 opacity-70' : 'border-sky-500/30'}`}
              >
                <div className="flex items-start gap-3">
                  <span className="text-sky-400 mt-0.5 flex-shrink-0">✦</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <TypeBadge type={ins.insight_type} />
                      {expired && <span className="text-[10px] text-slate-500 uppercase tracking-wider">Past</span>}
                    </div>
                    <p className="text-sm text-slate-200 leading-relaxed">{ins.content}</p>
                  </div>
                  <span className="text-[11px] text-slate-500 flex-shrink-0 whitespace-nowrap">
                    {formatDate(ins.insight_date)}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
