import { useState } from 'react'
import { useGoalTemplates, useCreateGoal } from '../../hooks/useGoals'
import type { GoalTemplate } from '../../types'

interface Props {
  onClose: () => void
}

export default function CreateGoalModal({ onClose }: Props) {
  const { data, isLoading } = useGoalTemplates()
  const createGoal = useCreateGoal()

  const [selectedTemplate, setSelectedTemplate] = useState<GoalTemplate | null>(null)
  const [name, setName] = useState('')
  const [targetValue, setTargetValue] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [cadence, setCadence] = useState('monthly')

  const templates = data?.templates ?? []

  const handleSelectTemplate = (t: GoalTemplate) => {
    setSelectedTemplate(t)
    setName(t.name)
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTemplate || !targetValue) return

    createGoal.mutate(
      {
        name: name.trim() || selectedTemplate.name,
        goal_type: selectedTemplate.goal_type,
        metric_source: selectedTemplate.metric_source,
        target_value: parseFloat(targetValue),
        target_date: targetDate || null,
        direction: selectedTemplate.direction,
        cadence,
      },
      { onSuccess: () => onClose() }
    )
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-slate-800 border border-slate-700 rounded-xl max-w-lg w-full mx-4 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-slate-100">
            {selectedTemplate ? 'Configure Goal' : 'New Goal'}
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5 overflow-y-auto">
          {!selectedTemplate ? (
            /* Step 1: Pick a template */
            <div className="space-y-3">
              <p className="text-sm text-slate-400 mb-4">
                Choose a goal type. Progress is tracked automatically from your account data.
              </p>
              {isLoading ? (
                <div className="space-y-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="h-16 bg-slate-700 rounded-lg animate-pulse" />
                  ))}
                </div>
              ) : templates.length === 0 ? (
                <p className="text-sm text-slate-500 text-center py-8">
                  No trackable goals available. Connect accounts first.
                </p>
              ) : (
                templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleSelectTemplate(t)}
                    className="w-full text-left bg-slate-900 hover:bg-slate-700 border border-slate-700 hover:border-slate-500 rounded-lg p-4 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-slate-100">{t.name}</span>
                      <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                        {t.goal_type.replace('_', ' ')}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">{t.description}</p>
                  </button>
                ))
              )}
            </div>
          ) : (
            /* Step 2: Configure details */
            <form onSubmit={handleCreate} className="space-y-4">
              <button
                type="button"
                onClick={() => setSelectedTemplate(null)}
                className="text-xs text-sky-400 hover:text-sky-300 transition-colors mb-2"
              >
                &larr; Back to templates
              </button>

              <div className="bg-slate-900 rounded-lg p-3 border border-slate-700">
                <span className="text-xs text-slate-500">Type</span>
                <p className="text-sm text-slate-200 mt-0.5">{selectedTemplate.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">{selectedTemplate.description}</p>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Goal Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  placeholder={selectedTemplate.name}
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1.5">
                  Target Value ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  placeholder="e.g. 50000"
                  required
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1.5">
                  Target Date (optional)
                </label>
                <input
                  type="date"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Tracking Cadence</label>
                <select
                  value={cadence}
                  onChange={(e) => setCadence(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                >
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={createGoal.isPending || !targetValue}
                className="w-full py-2.5 bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {createGoal.isPending ? 'Creating...' : 'Create Goal'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
