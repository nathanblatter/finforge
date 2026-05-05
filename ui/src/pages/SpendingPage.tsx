import { useState } from 'react'
import { useMonthlySpending, useTransactions } from '../hooks/useSpending'
import SpendSummary from '../components/spending/SpendSummary'
import CategoryDonut from '../components/spending/CategoryDonut'
import CardSplit from '../components/spending/CardSplit'
import FixedExpensesPanel from '../components/spending/FixedExpensesPanel'
import TransactionFeed from '../components/spending/TransactionFeed'
import Header from '../components/layout/Header'

function MonthSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // Generate last 12 months
  const months: { label: string; value: string }[] = []
  const now = new Date()
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    months.push({ label, value: val })
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
    >
      {months.map((m) => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
    </select>
  )
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

export default function SpendingPage() {
  const now = new Date()
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const [month, setMonth] = useState(defaultMonth)

  const { data: spending, isLoading: spendLoading } = useMonthlySpending(month)
  const { data: transactions, isLoading: txLoading } = useTransactions({ month })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Header title="Spending" />
        <MonthSelector value={month} onChange={setMonth} />
      </div>

      {spendLoading || !spending ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : (
        <SpendSummary data={spending} />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {spendLoading || !spending ? (
            <Skeleton className="h-64" />
          ) : (
            <CategoryDonut data={spending.by_category} />
          )}
        </div>
        <div className="space-y-4">
          {spendLoading || !spending ? (
            <>
              <Skeleton className="h-40" />
              <Skeleton className="h-48" />
            </>
          ) : (
            <>
              <CardSplit data={spending.by_card} />
              <FixedExpensesPanel data={spending.fixed_expenses} />
            </>
          )}
        </div>
      </div>

      {txLoading || !transactions ? (
        <Skeleton className="h-64" />
      ) : (
        <TransactionFeed transactions={transactions} />
      )}
    </div>
  )
}
