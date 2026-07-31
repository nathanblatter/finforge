import {
  useChargeGuardianFindings,
  useDismissChargeGuardianFinding,
  useMarkChargeGuardianFindingLegit,
} from '../../hooks/useSpending'
import { formatCurrency, formatDate } from '../../utils/format'
import type { ChargeGuardianFindingItem, ChargeGuardianKind } from '../../types'

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-slate-700 animate-pulse rounded-xl ${className}`} />
}

const KIND_LABELS: Record<ChargeGuardianKind, string> = {
  duplicate_charge: 'Possible duplicate',
  new_subscription: 'New subscription',
  trial_conversion: 'Trial converted to paid',
  gray_charge_creep: 'Gray-charge digest',
}

const KIND_COLORS: Record<ChargeGuardianKind, string> = {
  duplicate_charge: 'bg-rose-500/15 text-rose-400',
  new_subscription: 'bg-sky-500/15 text-sky-400',
  trial_conversion: 'bg-amber-500/15 text-amber-400',
  gray_charge_creep: 'bg-violet-500/15 text-violet-400',
}

function FindingCard({ finding }: { finding: ChargeGuardianFindingItem }) {
  const dismiss = useDismissChargeGuardianFinding()
  const markLegit = useMarkChargeGuardianFindingLegit()
  const busy = dismiss.isPending || markLegit.isPending

  return (
    <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-slate-100">{finding.merchant === '__digest__' ? 'Gray-charge digest' : finding.merchant}</span>
            {finding.amount !== null && (
              <span className="text-sm text-slate-300 tabular-nums">{formatCurrency(finding.amount)}</span>
            )}
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${KIND_COLORS[finding.kind]}`}>
              {KIND_LABELS[finding.kind] ?? finding.kind}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 whitespace-pre-line">{finding.detail}</p>
          <p className="text-[11px] text-slate-600 mt-0.5">{formatDate(finding.created_at)}</p>

          {finding.evidence_transactions.length > 0 && (
            <div className="mt-2 space-y-1">
              {finding.evidence_transactions.map((t) => (
                <div key={t.id} className="text-[11px] text-slate-500 flex items-center gap-2">
                  <span className="text-slate-600">•</span>
                  <span>{formatDate(t.date)}</span>
                  <span className="tabular-nums">{formatCurrency(t.amount)}</span>
                  <span className="text-slate-600">{t.merchant_name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <button
            onClick={() => dismiss.mutate(finding.id)}
            disabled={busy}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            onClick={() => markLegit.mutate(finding.id)}
            disabled={busy}
            className="text-xs text-slate-500 hover:text-emerald-400 transition-colors disabled:opacity-50"
          >
            Mark legit
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ChargeGuardianPanel() {
  const { data, isLoading } = useChargeGuardianFindings('open')
  const findings = data?.findings ?? []

  if (isLoading) return <Skeleton className="h-32" />
  if (findings.length === 0) return null

  return (
    <div className="bg-slate-800 border border-rose-500/30 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-rose-400 mb-1">Charge Guardian</h3>
      <p className="text-xs text-slate-500 mb-4">
        Fraud-style anomalies that complement price-hike alerts: duplicate charges, new subscriptions,
        trial-to-paid conversions, and small charges that quietly creep up.
      </p>
      <div className="space-y-3">
        {findings.map((f) => (
          <FindingCard key={f.id} finding={f} />
        ))}
      </div>
    </div>
  )
}
