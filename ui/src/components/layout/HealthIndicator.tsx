import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { HealthResponse } from '../../types'

const statusConfig = {
  ok:       { color: 'bg-emerald-500', label: 'Healthy' },
  degraded: { color: 'bg-yellow-500',  label: 'Degraded' },
  error:    { color: 'bg-rose-500',    label: 'Error' },
} as const

export default function HealthIndicator() {
  const { data, isError } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 60_000,
    retry: 1,
  })

  const status: 'ok' | 'degraded' | 'error' = isError ? 'error' : data?.status ?? 'error'
  const { color, label } = statusConfig[status]

  return (
    <div
      className="flex items-center gap-2 px-3 py-2"
      title={`Status: ${label}${data?.version ? ` (v${data.version})` : ''}`}
    >
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  )
}
