import { formatCurrency, formatPct } from '../../utils/format'
import type { CardSpend } from '../../types'

interface Props {
  data: CardSpend[]
}

export default function CardSplit({ data }: Props) {
  const total = data.reduce((sum, c) => sum + c.amount, 0)

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Spending by Card</h3>
      <div className="space-y-4">
        {data.map((card) => {
          const pct = total > 0 ? (card.amount / total) * 100 : 0
          return (
            <div key={card.alias}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm text-slate-300">{card.alias}</span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">{formatPct(pct)}</span>
                  <span className="text-sm font-medium text-slate-100">
                    {formatCurrency(card.amount)}
                  </span>
                </div>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-sky-500 rounded-full transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
