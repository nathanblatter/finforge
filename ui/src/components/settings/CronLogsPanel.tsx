import { useState, useEffect, useCallback } from 'react'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'
const TOKEN_KEY = 'finforge_token'

interface LogEntry {
  id: string
  job_name: string
  level: string
  message: string
  created_at: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-sky-400',
  WARNING: 'text-amber-400',
  ERROR: 'text-rose-400',
  CRITICAL: 'text-rose-500 font-bold',
  DEBUG: 'text-slate-500',
}

const JOB_LABELS: Record<string, string> = {
  scheduler: 'Scheduler',
  plaid_sync: 'Plaid Sync',
  schwab_sync: 'Schwab Sync',
  schwab_auth: 'Schwab Auth',
  market_data_sync: 'Market Data',
  goal_engine: 'Goal Engine',
  claude_engine: 'Claude Insights',
}

export default function CronLogsPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [jobFilter, setJobFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)

  const fetchLogs = useCallback(async () => {
    try {
      const token = localStorage.getItem(TOKEN_KEY)
      const params = new URLSearchParams()
      if (jobFilter) params.set('job', jobFilter)
      if (levelFilter) params.set('level', levelFilter)
      params.set('limit', '200')

      const headers: Record<string, string> = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json',
      }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const res = await fetch(`${BASE}/system/cron-logs?${params}`, { headers })
      if (res.ok) {
        const data = await res.json()
        setLogs(data.logs)
      }
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [jobFilter, levelFilter])

  useEffect(() => {
    setLoading(true)
    fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(fetchLogs, 5000)
    return () => clearInterval(interval)
  }, [autoRefresh, fetchLogs])

  // Derive unique job names from logs for the filter dropdown
  const jobNames = [...new Set(logs.map((l) => l.job_name))].sort()

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Cron Logs
        </h2>
        <div className="flex items-center gap-3">
          {/* Job filter */}
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-sky-500"
          >
            <option value="">All Jobs</option>
            {Object.entries(JOB_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>

          {/* Level filter */}
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-sky-500"
          >
            <option value="">All Levels</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
              autoRefresh
                ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                : 'bg-slate-900 border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            {autoRefresh ? 'Live' : 'Auto-refresh'}
          </button>

          {/* Manual refresh */}
          <button
            onClick={() => { setLoading(true); fetchLogs() }}
            className="text-xs px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-slate-400 hover:text-slate-200 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div className="space-y-1">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-5 bg-slate-700 rounded animate-pulse" />
          ))}
        </div>
      ) : logs.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">
          No cron logs yet. Trigger "Run All Jobs Now" above to generate logs.
        </p>
      ) : (
        <div className="bg-slate-900 border border-slate-700 rounded-lg overflow-hidden">
          <div className="max-h-[500px] overflow-y-auto font-mono text-xs leading-relaxed">
            {logs.map((log) => {
              const ts = new Date(log.created_at)
              const timeStr = ts.toLocaleTimeString('en-US', { hour12: false })
              const dateStr = ts.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              const levelColor = LEVEL_COLORS[log.level] ?? 'text-slate-400'
              const jobLabel = JOB_LABELS[log.job_name] ?? log.job_name

              return (
                <div
                  key={log.id}
                  className="flex gap-0 px-3 py-1 hover:bg-slate-800/60 border-b border-slate-800/50 last:border-0"
                >
                  <span className="text-slate-600 w-[110px] shrink-0">
                    {dateStr} {timeStr}
                  </span>
                  <span className={`w-[70px] shrink-0 ${levelColor}`}>
                    {log.level}
                  </span>
                  <span className="text-slate-500 w-[110px] shrink-0 truncate">
                    {jobLabel}
                  </span>
                  <span className="text-slate-300 break-all min-w-0">
                    {log.message}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-slate-600">
          {logs.length} entries{autoRefresh ? ' — refreshing every 5s' : ''}
        </span>
      </div>
    </div>
  )
}
