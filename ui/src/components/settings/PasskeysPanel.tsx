import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import {
  defaultPasskeyName,
  deletePasskey,
  listPasskeys,
  passkeysSupported,
  registerPasskey,
  type PasskeyInfo,
} from '../../api/passkeys'

/** Settings → Passkeys: list, add, and remove the current user's passkeys. */
export default function PasskeysPanel() {
  const { token } = useAuth()
  const [passkeys, setPasskeys] = useState<PasskeyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState(defaultPasskeyName())

  const load = useCallback(async () => {
    if (!token) return
    try {
      setPasskeys(await listPasskeys(token))
    } catch (err: any) {
      setError(err.message || 'Failed to load passkeys')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  async function handleAdd() {
    if (!token) return
    setError('')
    setBusy(true)
    try {
      await registerPasskey(token, name.trim() || 'Passkey')
      setAdding(false)
      setName(defaultPasskeyName())
      await load()
    } catch (err: any) {
      if (err?.name !== 'NotAllowedError') setError(err.message || 'Could not add passkey')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(p: PasskeyInfo) {
    if (!token) return
    setError('')
    setBusy(true)
    try {
      await deletePasskey(token, p.id)
      await load()
    } catch (err: any) {
      setError(err.message || 'Could not remove passkey')
    } finally {
      setBusy(false)
    }
  }

  const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : 'never')

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Passkeys</h2>
          <p className="text-xs text-slate-500 mt-1">
            Sign in with Face ID, Touch ID, or a hardware key instead of a password.
          </p>
        </div>
        {passkeysSupported() && (
          <button
            onClick={() => { setAdding(!adding); setError('') }}
            className="px-3 py-1.5 text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            {adding ? 'Cancel' : 'Add Passkey'}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-500/30 rounded-lg px-4 py-3 text-sm text-rose-300 mb-4">
          {error}
        </div>
      )}

      {adding && (
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            placeholder="Passkey name"
            className="flex-1 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:border-sky-500"
          />
          <button
            onClick={handleAdd}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg transition-colors"
          >
            {busy ? 'Waiting...' : 'Create'}
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : passkeys.length === 0 ? (
        <p className="text-sm text-slate-500">No passkeys yet.</p>
      ) : (
        <div className="space-y-2">
          {passkeys.map((p) => (
            <div key={p.id} className="flex items-center justify-between border border-slate-700 bg-slate-900/50 rounded-lg px-4 py-3">
              <div>
                <div className="text-sm font-medium text-slate-200">{p.name}</div>
                <div className="text-xs text-slate-500">
                  Added {fmt(p.created_at)} &middot; Last used {fmt(p.last_used_at)}
                  {p.backed_up && ' · Synced'}
                </div>
              </div>
              <button
                onClick={() => handleDelete(p)}
                disabled={busy}
                className="px-3 py-1.5 text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 disabled:text-slate-600 rounded-lg transition-colors"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
