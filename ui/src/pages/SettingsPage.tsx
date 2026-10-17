import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { useAuth } from '../hooks/useAuth'
import Header from '../components/layout/Header'
import CronLogsPanel from '../components/settings/CronLogsPanel'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'
const TOKEN_KEY = 'finforge_token'

interface UserInfo {
  id: string
  username: string
  is_active: boolean
  created_at: string
  services: string[]
}

interface ServiceInfo {
  name: string
  key: string
  connected: boolean
  details: Record<string, any>
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Error ${res.status}`)
  }
  return res.json() as Promise<T>
}

export default function SettingsPage() {
  const { token } = useAuth()
  const [users, setUsers] = useState<UserInfo[]>([])
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [syncRunning, setSyncRunning] = useState(false)

  // Add user form
  const [showAddUser, setShowAddUser] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [addLoading, setAddLoading] = useState(false)

  // Plaid Link
  const [linkToken, setLinkToken] = useState<string | null>(null)
  const [plaidStatuses, setPlaidStatuses] = useState<{institution: string, accounts: string[], linked: boolean}[]>([])


  async function loadData() {
    setLoading(true)
    try {
      const [u, s] = await Promise.all([
        apiFetch<UserInfo[]>('/users'),
        apiFetch<ServiceInfo[]>('/users/services'),
      ])
      setUsers(u)
      setServices(s)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [token])

  // Load Plaid statuses
  useEffect(() => {
    apiFetch<{institution: string, accounts: string[], linked: boolean}[]>('/plaid/status')
      .then(setPlaidStatuses)
      .catch(() => {})
  }, [token])

  // Handle OAuth return — re-open Plaid Link to complete the flow
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('oauth') === 'true') {
      // Retrieve stored link token and re-initialize Link
      const storedToken = sessionStorage.getItem('plaid_link_token')
      if (storedToken) {
        setLinkToken(storedToken)
      } else {
        // Link token was lost (e.g. session cleared or different tab) — the OAuth
        // flow can't be resumed. Surface this instead of failing silently.
        setError('Bank linking session expired. Please start "Link a bank" again.')
      }
      // Clean up URL
      window.history.replaceState({}, '', '/settings')
    }
    if (params.get('schwab') === 'connected') {
      setSuccess('Schwab reconnected — tokens saved. The nightly sync will use them automatically.')
      window.history.replaceState({}, '', '/settings')
    }
  }, [])

  // Plaid Link handlers
  async function startPlaidLink() {
    clearMessages()
    try {
      const data = await apiFetch<{ link_token: string }>('/plaid/link-token', { method: 'POST' })
      setLinkToken(data.link_token)
      // Store for OAuth return
      sessionStorage.setItem('plaid_link_token', data.link_token)
    } catch (err: any) {
      setError(err.message)
    }
  }

  const onPlaidSuccess = useCallback(async (publicToken: string, metadata: any) => {
    clearMessages()
    try {
      const accounts = (metadata.accounts || []).map((a: any) => ({
        id: a.id,
        name: a.name,
        type: a.type,
        subtype: a.subtype,
      }))
      const data = await apiFetch<{ status: string; institution: string; accounts_linked: string[] }>(
        '/plaid/exchange',
        {
          method: 'POST',
          body: JSON.stringify({
            public_token: publicToken,
            institution_name: metadata.institution?.name || 'Unknown',
            accounts,
          }),
        },
      )
      setSuccess(`Linked ${data.institution}: ${data.accounts_linked.join(', ')}`)
      setLinkToken(null)
      // Reload statuses
      const statuses = await apiFetch<{institution: string, accounts: string[], linked: boolean}[]>('/plaid/status')
      setPlaidStatuses(statuses)
      await loadData()
    } catch (err: any) {
      setError(err.message)
    }
  }, [])

  const { open: openPlaidLink, ready: plaidReady } = usePlaidLink({
    token: linkToken,
    onSuccess: onPlaidSuccess,
    onExit: () => setLinkToken(null),
  })

  useEffect(() => {
    if (linkToken && plaidReady) openPlaidLink()
  }, [linkToken, plaidReady, openPlaidLink])

  function clearMessages() { setError(''); setSuccess('') }

  async function handleAddUser(e: FormEvent) {
    e.preventDefault()
    clearMessages()
    setAddLoading(true)
    try {
      await apiFetch('/users', {
        method: 'POST',
        body: JSON.stringify({ username: newUsername }),
      })
      setNewUsername('')
      setShowAddUser(false)
      setSuccess('User created')
      await loadData()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setAddLoading(false)
    }
  }

  async function handleToggleActive(user: UserInfo) {
    clearMessages()
    try {
      await apiFetch(`/users/${user.id}`, {
        method: 'PUT',
        body: JSON.stringify({ is_active: !user.is_active }),
      })
      await loadData()
    } catch (err: any) {
      setError(err.message)
    }
  }

  async function handleDeleteUser(user: UserInfo) {
    clearMessages()
    if (!confirm(`Delete user "${user.username}"? This cannot be undone.`)) return
    try {
      await apiFetch(`/users/${user.id}`, { method: 'DELETE' })
      setSuccess(`User "${user.username}" deleted`)
      await loadData()
    } catch (err: any) {
      setError(err.message)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Header title="Settings" />
        <div className="animate-pulse space-y-4">
          <div className="h-40 bg-slate-800 border border-slate-700 rounded-xl" />
          <div className="h-60 bg-slate-800 border border-slate-700 rounded-xl" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1000px]">
      <Header title="Settings" />

      {error && (
        <div className="bg-rose-950/40 border border-rose-500/30 rounded-lg px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-lg px-4 py-3 text-sm text-emerald-300">
          {success}
        </div>
      )}

      {/* Connected Services */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Connected Services
          </h2>
          <button
            onClick={() => { window.location.href = '/api/v1/auth/schwab/login' }}
            className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            Reconnect Schwab
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {services.map((svc) => (
            <div
              key={svc.key}
              className={`border rounded-lg p-4 ${
                svc.connected
                  ? 'border-emerald-500/30 bg-emerald-950/20'
                  : 'border-slate-600 bg-slate-900/50'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2 h-2 rounded-full ${svc.connected ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                <span className="text-sm font-medium text-slate-200">{svc.name}</span>
              </div>
              <div className="text-xs text-slate-500">
                {svc.connected ? 'Connected' : 'Not configured'}
              </div>
              {svc.connected && svc.details.accounts && (
                <div className="mt-2 space-y-0.5">
                  {(svc.details.accounts as string[]).map((a) => (
                    <div key={a} className="text-xs text-slate-400">{a}</div>
                  ))}
                </div>
              )}
              {svc.connected && svc.details.environment && (
                <div className="text-xs text-slate-400 mt-1">
                  Env: {svc.details.environment}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Data Sync */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
              Data Sync
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Manually trigger all cron jobs: Plaid sync, Schwab sync, market data, goal snapshots, insights, and alerts.
            </p>
          </div>
          <button
            onClick={async () => {
              clearMessages()
              setSyncRunning(true)
              try {
                await apiFetch('/system/run-jobs', { method: 'POST' })
                setSuccess('All cron jobs triggered. Data will update in the background.')
              } catch (err: any) {
                setError(err.message)
              } finally {
                setSyncRunning(false)
              }
            }}
            disabled={syncRunning}
            className="px-4 py-2 text-sm font-medium bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors flex items-center gap-2"
          >
            {syncRunning ? (
              <>
                <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Running...
              </>
            ) : (
              'Run All Jobs Now'
            )}
          </button>
        </div>
      </div>

      {/* Bank Connections (Plaid) */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Bank Connections
          </h2>
          <button
            onClick={startPlaidLink}
            className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            Link Bank Account
          </button>
        </div>

        {plaidStatuses.length === 0 ? (
          <p className="text-sm text-slate-500">No bank accounts linked yet. Click "Link Bank Account" to connect Wells Fargo, Amex, or other institutions.</p>
        ) : (
          <div className="space-y-3">
            {plaidStatuses.map((inst) => (
              <div key={inst.institution} className="border border-emerald-500/30 bg-emerald-950/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-sm font-medium text-slate-200">{inst.institution}</span>
                </div>
                <div className="space-y-0.5">
                  {inst.accounts.map((a, i) => (
                    <div key={i} className="text-xs text-slate-400">{a}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Users */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
            Users
          </h2>
          <button
            onClick={() => { setShowAddUser(!showAddUser); clearMessages() }}
            className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            {showAddUser ? 'Cancel' : 'Add User'}
          </button>
        </div>

        {/* Add user form */}
        {showAddUser && (
          <form onSubmit={handleAddUser} className="mb-4 p-4 bg-slate-900 border border-slate-700 rounded-lg">
            <p className="text-xs text-slate-500 mb-3">
              Users sign in through Squawk; the username only labels the FinForge account.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Username</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-sky-500"
                  required
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={addLoading || !newUsername}
              className="px-4 py-2 text-sm bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
            >
              {addLoading ? 'Creating...' : 'Create User'}
            </button>
          </form>
        )}

        {/* Users table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase tracking-wider border-b border-slate-700">
                <th className="pb-2 pr-4">Username</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2 pr-4">Created</th>
                <th className="pb-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-slate-700/20 transition-colors">
                  <td className="py-3 pr-4 font-medium text-slate-100">{user.username}</td>
                  <td className="py-3 pr-4">
                    <button
                      onClick={() => handleToggleActive(user)}
                      className={`text-xs px-2 py-0.5 rounded-full cursor-pointer transition-colors ${
                        user.is_active
                          ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-400 hover:bg-rose-500/30'
                      }`}
                    >
                      {user.is_active ? 'Active' : 'Inactive'}
                    </button>
                  </td>
                  <td className="py-3 pr-4 text-slate-400">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-3 text-right space-x-2">
                    <button
                      onClick={() => handleDeleteUser(user)}
                      className="text-xs text-rose-400 hover:text-rose-300 transition-colors"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cron Logs */}
      <CronLogsPanel />

    </div>
  )
}
