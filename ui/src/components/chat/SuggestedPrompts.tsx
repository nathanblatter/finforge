const PROMPTS = [
  'Am I on track to max my Roth this year?',
  "How does this month's spending compare to last month?",
  'What categories should I cut to hit my savings goal faster?',
]

interface Props {
  onSelect: (prompt: string) => void
  disabled: boolean
}

export default function SuggestedPrompts({ onSelect, disabled }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      {PROMPTS.map((prompt) => (
        <button
          key={prompt}
          onClick={() => onSelect(prompt)}
          disabled={disabled}
          className="bg-slate-800 border border-slate-700 hover:border-sky-500/50 hover:text-sky-400 text-slate-400 text-sm rounded-full px-3 py-1.5 cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-left"
        >
          {prompt}
        </button>
      ))}
    </div>
  )
}
