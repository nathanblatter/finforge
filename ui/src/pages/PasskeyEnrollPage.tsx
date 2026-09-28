import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { defaultPasskeyName, passkeysSupported, registerPasskey } from '../api/passkeys'

/**
 * Magic-link landing page: /passkeys/enroll?token=<enrollment token>.
 * Registers a passkey using only the short-lived token, then signs the user in.
 */
export default function PasskeyEnrollPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const { setSession } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState(defaultPasskeyName())
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleEnroll() {
    setError('')
    setLoading(true)
    try {
      const data = await registerPasskey(token, name.trim() || 'Passkey')
      setSession(data.access_token)
      navigate('/', { replace: true })
    } catch (err: any) {
      if (err?.name !== 'NotAllowedError') setError(err.message || 'Enrollment failed')
    } finally {
      setLoading(false)
    }
  }

  const supported = passkeysSupported()

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          <div className="flex items-center gap-2.5 mb-1">
            <img src="/finforge_minimal.png" alt="FinForge" className="w-7 h-7 rounded-md" />
            <h1 className="text-2xl font-bold text-sky-400">FinForge</h1>
          </div>
          <p className="text-sm text-slate-400 mb-6">Set up a passkey for your account</p>

          {!token ? (
            <p className="text-rose-400 text-sm">This link is missing its token. Ask for a new enrollment link.</p>
          ) : !supported ? (
            <p className="text-rose-400 text-sm">This browser doesn't support passkeys. Open the link in Safari or Chrome.</p>
          ) : (
            <div className="space-y-4">
              <div>
                <label htmlFor="passkey-name" className="block text-xs font-medium text-slate-400 mb-1.5">Passkey name</label>
                <input
                  id="passkey-name"
                  type="text"
                  value={name}
                  maxLength={100}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-sky-500"
                />
                <p className="text-xs text-slate-500 mt-1.5">
                  Your device will ask for Face ID, Touch ID, or your device passcode. The link expires after a few minutes.
                </p>
              </div>

              {error && <p className="text-rose-400 text-sm">{error}</p>}

              <button
                type="button"
                onClick={handleEnroll}
                disabled={loading}
                className="w-full py-3 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg transition-colors"
              >
                {loading ? 'Waiting for your device...' : 'Create passkey & sign in'}
              </button>
            </div>
          )}
        </div>
        <div className="mt-4 flex justify-center text-xs text-slate-500">
          <Link to="/login" className="hover:text-sky-400 transition-colors">Back to sign in</Link>
        </div>
      </div>
    </div>
  )
}
