import Header from '../components/layout/Header'
import KeyMetrics from '../components/dashboard/KeyMetrics'
import NetWorthChart from '../components/dashboard/NetWorthChart'
import AccountCards from '../components/dashboard/AccountCards'
import InsightBanner from '../components/dashboard/InsightBanner'
import { useSummary } from '../hooks/useSummary'
import { useBalances } from '../hooks/useBalances'
import { useInsights } from '../hooks/useInsights'

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-800 border border-slate-700 rounded-xl ${className ?? ''}`} />
}

function ErrorCard({ message }: { message: string }) {
  return (
    <div className="bg-rose-950/40 border border-rose-800/50 rounded-xl p-4 text-sm text-rose-400">
      {message}
    </div>
  )
}

export default function DashboardPage() {
  const { data: summary, isLoading: summaryLoading, error: summaryError } = useSummary()
  const { data: balances, isLoading: balancesLoading, error: balancesError } = useBalances()
  const { data: insightsData } = useInsights()

  const latestInsight = insightsData?.insights?.[0]

  return (
    <div className="flex flex-col gap-6 max-w-[1400px] mx-auto">
      <Header title="Dashboard" />

      {/* Key Metrics */}
      {summaryError
        ? <ErrorCard message="Failed to load summary. Check API connection." />
        : summaryLoading || !summary
          ? <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
          : <KeyMetrics summary={summary} />
      }

      {/* Net Worth Trend */}
      {summaryLoading
        ? <Skeleton className="h-64" />
        : <NetWorthChart />
      }

      {/* Account Cards */}
      {balancesError
        ? <ErrorCard message="Failed to load account balances." />
        : balancesLoading || !balances
          ? (
            <div>
              <div className="h-4 w-20 bg-slate-800 rounded animate-pulse mb-3" />
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-36" />)}
              </div>
            </div>
          )
          : <AccountCards balances={balances} />
      }

      {/* Insight Banner */}
      {latestInsight && <InsightBanner insight={latestInsight} />}
    </div>
  )
}
