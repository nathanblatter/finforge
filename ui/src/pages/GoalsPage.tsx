import { useState } from 'react'
import Header from '../components/layout/Header'
import GoalCard from '../components/goals/GoalCard'
import GoalDetailModal from '../components/goals/GoalDetailModal'
import CreateGoalModal from '../components/goals/CreateGoalModal'
import { useGoals } from '../hooks/useGoals'
import type { GoalProgressResponse } from '../types'

type FilterTab = 'all' | 'active' | 'completed'

const TABS: { label: string; value: FilterTab }[] = [
  { label: 'All',       value: 'all' },
  { label: 'Active',    value: 'active' },
  { label: 'Completed', value: 'completed' },
]

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-800 border border-slate-700 rounded-xl animate-pulse ${className}`} />
}

function filterGoals(goals: GoalProgressResponse[], tab: FilterTab): GoalProgressResponse[] {
  if (tab === 'all') return goals
  if (tab === 'completed') return goals.filter((g) => g.status === 'completed')
  return goals.filter((g) => g.status === 'active' || g.status === 'paused')
}

export default function GoalsPage() {
  const [activeTab, setActiveTab] = useState<FilterTab>('all')
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading, error } = useGoals()

  const allGoals = data?.goals ?? []
  const filtered = filterGoals(allGoals, activeTab)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Header title="Goals" />
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + New Goal
          </button>
        <div className="flex gap-1 bg-slate-800 border border-slate-700 rounded-lg p-1">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={[
                'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                activeTab === tab.value
                  ? 'bg-slate-700 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200',
              ].join(' ')}
            >
              {tab.label}
            </button>
          ))}
        </div>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-800/50 rounded-xl p-4 text-sm text-rose-400">
          Failed to load goals. Check API connection.
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      )}

      {!isLoading && !error && (
        filtered.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                onClick={() => setSelectedGoalId(goal.id)}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <p className="text-slate-400 text-sm font-medium">No goals yet</p>
            <p className="text-slate-600 text-xs">Create an auto-tracked goal to get started.</p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              + New Goal
            </button>
          </div>
        )
      )}

      {selectedGoalId && (
        <GoalDetailModal
          goalId={selectedGoalId}
          onClose={() => setSelectedGoalId(null)}
        />
      )}

      {showCreate && (
        <CreateGoalModal onClose={() => setShowCreate(false)} />
      )}
    </div>
  )
}
