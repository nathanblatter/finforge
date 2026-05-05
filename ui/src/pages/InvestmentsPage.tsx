import { useBrokerage, useIRA } from '../hooks/useInvestments'
import BrokeragePanel from '../components/investments/BrokeragePanel'
import IRAPanel from '../components/investments/IRAPanel'
import Header from '../components/layout/Header'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function InvestmentsPage() {
  const { data: brokerage, isLoading: brokerageLoading } = useBrokerage()
  const { data: ira, isLoading: iraLoading } = useIRA()

  return (
    <div className="space-y-8">
      <Header title="Investments" />

      {/* Brokerage — primary */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-base font-semibold text-slate-200">Schwab Brokerage</h2>
          <span className="text-xs bg-sky-500/20 text-sky-400 px-2 py-0.5 rounded-full">
            Savings Balance
          </span>
        </div>
        {brokerageLoading || !brokerage ? (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28" />)}
            </div>
            <Skeleton className="h-64" />
          </div>
        ) : (
          <BrokeragePanel data={brokerage} />
        )}
      </section>

      {/* Divider */}
      <div className="border-t border-slate-700" />

      {/* IRA — secondary, visually distinct */}
      <section>
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-200">Retirement Accounts</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Excluded from savings balance — long-term retirement funds
          </p>
        </div>
        {iraLoading || !ira ? (
          <Skeleton className="h-64" />
        ) : (
          <IRAPanel data={ira} />
        )}
      </section>
    </div>
  )
}
