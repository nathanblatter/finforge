import { formatCurrency } from '../../utils/format'
import type { OptionPositionDetail } from '../../types'

const STRATEGY_LABEL: Record<OptionPositionDetail['strategy'], string> = {
  covered_call: 'Covered call',
  cash_secured_put: 'Cash-secured put',
  naked_call: 'Short call (uncovered)',
  long_call: 'Long call',
  long_put: 'Long put',
}

interface Props {
  options: OptionPositionDetail[]
  premiumYtd: number
}

/** Open option contracts (e.g. written covered calls) with premium and assignment outlook. */
export default function OptionsPanel({ options, premiumYtd }: Props) {
  if (options.length === 0 && !premiumYtd) return null

  const signed = (n: number) => `${n >= 0 ? '+' : ''}${formatCurrency(n)}`

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Options</h3>
        <div className="text-xs text-slate-500">
          Premium collected YTD{' '}
          <span className="text-emerald-400 font-medium">{formatCurrency(premiumYtd)}</span>
        </div>
      </div>

      {options.length === 0 ? (
        <p className="text-sm text-slate-500">No open contracts.</p>
      ) : (
        <div className="space-y-3">
          {options.map((o) => {
            const short = o.contracts < 0
            const n = Math.abs(o.contracts)
            const pl = o.unrealized_gain_loss
            const expiring = o.days_to_expiry <= 7
            const moneyness =
              o.in_the_money == null ? null : o.in_the_money ? 'In the money' : 'Out of the money'
            const distance =
              o.underlying_price != null
                ? ((o.strike - o.underlying_price) / o.underlying_price) * 100
                : null

            return (
              <div key={o.symbol} className="border border-slate-700 bg-slate-900/50 rounded-lg p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-slate-100">{o.display}</div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {short ? 'Sold' : 'Bought'} {n} contract{n === 1 ? '' : 's'} &middot; {STRATEGY_LABEL[o.strategy]}
                      {o.strategy === 'naked_call' && (
                        <span className="ml-1 text-amber-400">&middot; not covered by shares</span>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-medium ${expiring ? 'text-amber-400' : 'text-slate-300'}`}>
                      {o.days_to_expiry < 0
                        ? 'Expired'
                        : o.days_to_expiry === 0
                          ? 'Expires today'
                          : `${o.days_to_expiry} day${o.days_to_expiry === 1 ? '' : 's'} left`}
                    </div>
                    {moneyness && (
                      <div className={`text-xs ${o.in_the_money ? 'text-amber-400' : 'text-slate-500'}`}>
                        {moneyness}
                        {distance != null && ` (${o.underlying} ${formatCurrency(o.underlying_price!)}, strike ${distance >= 0 ? '+' : ''}${distance.toFixed(1)}%)`}
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-xs">
                  <div>
                    <div className="text-slate-500">{short ? 'Premium received' : 'Premium paid'}</div>
                    <div className="text-slate-200 font-medium">
                      {o.premium != null ? formatCurrency(o.premium) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{short ? 'Cost to close' : 'Current value'}</div>
                    <div className="text-slate-200 font-medium">{formatCurrency(Math.abs(o.market_value))}</div>
                  </div>
                  <div>
                    <div className="text-slate-500">Unrealized P&L</div>
                    <div className={`font-medium ${pl == null ? 'text-slate-600' : pl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pl != null ? signed(pl) : '—'}
                    </div>
                  </div>
                  {o.if_assigned_gain != null && (
                    <div>
                      <div className="text-slate-500">If called away</div>
                      <div className={`font-medium ${o.if_assigned_gain >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {signed(o.if_assigned_gain)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
