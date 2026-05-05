import type { GoalAlertResponse } from '../../types'
import { formatDate } from '../../utils/format'

function alertTypeBadge(alertType: string): string {
  switch (alertType) {
    case 'off_track':  return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
    case 'at_risk':    return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
    case 'completed':  return 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
    default:           return 'bg-slate-700/60 text-slate-400 border border-slate-600'
  }
}

function alertTypeLabel(alertType: string): string {
  switch (alertType) {
    case 'off_track':  return 'Off Track'
    case 'at_risk':    return 'At Risk'
    case 'completed':  return 'Completed'
    default:           return alertType.replace(/_/g, ' ')
  }
}

interface AlertsListProps {
  alerts: GoalAlertResponse[]
  onAcknowledge: (id: string) => void
  isAcknowledging: boolean
}

export default function AlertsList({ alerts, onAcknowledge, isAcknowledging }: AlertsListProps) {
  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <p className="text-slate-400 text-sm font-medium">No alerts</p>
        <p className="text-slate-600 text-xs">You're all caught up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col divide-y divide-slate-700/60">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className={`flex items-start gap-4 py-4 px-1 transition-opacity ${alert.is_acknowledged ? 'opacity-50' : ''}`}
        >
          <span className={`shrink-0 mt-0.5 text-xs font-medium px-2 py-0.5 rounded-full ${alertTypeBadge(alert.alert_type)}`}>
            {alertTypeLabel(alert.alert_type)}
          </span>

          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-200 truncate">{alert.goal_name}</p>
            <p className="text-sm text-slate-400 mt-0.5">{alert.message}</p>
            <p className="text-xs text-slate-600 mt-1">{formatDate(alert.created_at)}</p>
          </div>

          <div className="shrink-0 flex flex-col items-end gap-1">
            {alert.is_acknowledged ? (
              <div className="text-right">
                <span className="text-xs text-slate-500 font-medium">Acknowledged</span>
                {alert.acknowledged_at && (
                  <p className="text-xs text-slate-600">{formatDate(alert.acknowledged_at)}</p>
                )}
              </div>
            ) : (
              <button
                onClick={() => onAcknowledge(alert.id)}
                disabled={isAcknowledging}
                className="text-xs font-medium px-2.5 py-1 rounded-md bg-slate-700 text-slate-300 hover:bg-slate-600 hover:text-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Acknowledge
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
