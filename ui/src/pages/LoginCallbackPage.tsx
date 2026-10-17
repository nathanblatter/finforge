import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { clearStashedPkce, squawkApi, SquawkAuthError, takeStashedPkce } from '../api/squawk'

/**
 * Squawk sends the browser here with `code` + `state` after a successful
 * ceremony. We check `state` against the PKCE pair stashed when the
 * authorization started, trade the code (plus verifier) for a FinForge
 * session token at /auth/squawk/exchange, and land on the dashboard.
 */
export default function LoginCallbackPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { setSession } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // codes are single use; never exchange twice (StrictMode double-invoke)
    ran.current = true

    const params = new URLSearchParams(location.search)
    const squawkError = params.get('error')
    const code = params.get('code')
    const state = params.get('state')

    if (squawkError) {
      clearStashedPkce()
      setError(squawkError === 'access_denied' ? 'Sign-in was cancelled.' : `Sign-in failed (${squawkError}).`)
      return
    }
    if (!code || !state) {
      setError('Malformed sign-in response. Start over.')
      return
    }
    const stashed = takeStashedPkce()
    if (!stashed || stashed.state !== state) {
      clearStashedPkce()
      setError('This sign-in attempt expired or was already used. Start over.')
      return
    }

    squawkApi.exchange(code, stashed.verifier)
      .then((tokens) => {
        clearStashedPkce()
        setSession(tokens.access_token)
        navigate('/', { replace: true })
      })
      .catch((err: unknown) => {
        clearStashedPkce()
        setError(err instanceof SquawkAuthError ? err.message : 'Sign-in failed. Start over.')
      })
  }, [location.search, navigate, setSession])

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          <div className="flex items-center gap-2.5 mb-6">
            <img src="/finforge_minimal.png" alt="FinForge" className="w-7 h-7 rounded-md" />
            <h1 className="text-2xl font-bold text-sky-400">FinForge</h1>
          </div>
          {error ? (
            <div className="space-y-4">
              <p className="text-rose-400 text-sm" role="alert">{error}</p>
              <Link to="/login" className="block text-center w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-lg transition-colors">
                Back to sign in
              </Link>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Finishing sign-in...</p>
          )}
        </div>
      </div>
    </div>
  )
}
