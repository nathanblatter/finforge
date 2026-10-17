import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { startAuthentication } from '@simplewebauthn/browser'
import { squawkApi, startAuthorization, SquawkAuthError, type SquawkConfig } from '../api/squawk'

/**
 * Sign-in through Squawk (Nathan's auth service) — the only way in.
 *
 * Without `?login_challenge=` this page offers "Sign in with Squawk", which
 * generates PKCE in the browser and sends it to Squawk's /oauth/authorize.
 * Squawk parks the request and sends the browser back here with a
 * `login_challenge`; we complete the owner-passkey, account-passkey or
 * emailed-code ceremony through the API proxies and follow `redirect_to`
 * (our /login/callback, which exchanges the code for a FinForge session).
 *
 * The same challenge page serves Squawk-driven sign-ins that start elsewhere,
 * e.g. approving the Claude connector while already logged in to FinForge.
 */

const CALLBACK_ERRORS: Record<string, string> = {
  access_denied: 'Sign-in was cancelled.',
  state_mismatch: 'This sign-in attempt expired or was already used. Start over.',
  invalid_token: 'Squawk returned a token FinForge could not verify.',
  invalid_grant: 'The sign-in code was rejected. Start over.',
  invalid_request: 'Malformed sign-in response. Start over.',
  signup_closed: 'No account exists for that identity.',
  server_error: 'The sign-in service is unavailable. Try again shortly.',
  login_expired: 'This sign-in attempt expired. Start over.',
}

const primaryBtn =
  'w-full py-3 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2'
const secondaryBtn =
  'w-full py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 disabled:opacity-60 text-slate-200 text-sm font-medium rounded-lg transition-colors'
const inputClass =
  'w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-sky-500'

function isCancelled(err: unknown): boolean {
  return err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'AbortError')
}

export default function LoginPage() {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const loginChallenge = params.get('login_challenge')
  const callbackError = params.get('error')

  const [config, setConfig] = useState<SquawkConfig | null | 'unavailable'>(null)
  const [error, setError] = useState<string | null>(
    callbackError ? (CALLBACK_ERRORS[callbackError] ?? `Sign-in failed (${callbackError}).`) : null,
  )
  const [busy, setBusy] = useState(false)

  // Challenge-page state
  const [method, setMethod] = useState<'choose' | 'email'>('choose')
  const [email, setEmail] = useState('')
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [code, setCode] = useState('')

  useEffect(() => {
    if (loginChallenge) return
    squawkApi.config().then(setConfig).catch(() => setConfig('unavailable'))
  }, [loginChallenge])

  const fail = (err: unknown, fallback: string) => {
    setError(err instanceof SquawkAuthError ? err.message : fallback)
  }

  const startSquawk = async () => {
    if (!config || config === 'unavailable') return
    setError(null)
    setBusy(true)
    try {
      window.location.assign(await startAuthorization(config))
    } catch {
      setError('Could not start sign-in.')
      setBusy(false)
    }
  }

  /** Run a passkey assertion: `owner` uses Nathan's Squawk passkey, `account`
   *  a passkey registered on a FinForge account in Squawk. */
  const signInWithPasskey = async (kind: 'owner' | 'account') => {
    if (!loginChallenge) return
    setError(null)
    setBusy(true)
    try {
      const begin = kind === 'owner'
        ? await squawkApi.ownerBegin(loginChallenge)
        : await squawkApi.passkeyBegin(loginChallenge)
      const credential = await startAuthentication({ optionsJSON: begin.options.publicKey })
      const { redirect_to } = kind === 'owner'
        ? await squawkApi.ownerFinish(begin.challenge_id, credential)
        : await squawkApi.passkeyFinish(begin.challenge_id, credential)
      window.location.assign(redirect_to)
    } catch (err) {
      // Cancelling the OS prompt is not an error worth shouting about.
      if (!isCancelled(err)) fail(err, 'Passkey sign-in failed.')
      setBusy(false)
    }
  }

  const sendCode = async (e: FormEvent) => {
    e.preventDefault()
    if (!loginChallenge) return
    setError(null)
    setBusy(true)
    try {
      const { challenge_id } = await squawkApi.emailBegin(loginChallenge, email.trim())
      setChallengeId(challenge_id)
      setCode('')
    } catch (err) {
      fail(err, 'Could not send a code.')
    } finally {
      setBusy(false)
    }
  }

  const submitCode = async (e: FormEvent) => {
    e.preventDefault()
    if (!challengeId) return
    setError(null)
    setBusy(true)
    try {
      const { redirect_to } = await squawkApi.emailFinish(challengeId, code)
      window.location.assign(redirect_to)
    } catch (err) {
      fail(err, 'That code was not accepted.')
      if (err instanceof SquawkAuthError && err.code !== 'code_rejected') setChallengeId(null)
      setBusy(false)
    }
  }

  let body: React.ReactNode
  if (loginChallenge && method === 'email' && challengeId) {
    body = (
      <form onSubmit={submitCode} className="space-y-4">
        <p className="text-sm text-slate-400">
          We emailed a 6-digit code to <span className="text-slate-200">{email}</span>. It expires in 10 minutes.
        </p>
        <input
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="6-digit code"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-center text-2xl tracking-[0.5em] placeholder:text-slate-600 placeholder:tracking-normal placeholder:text-base focus:outline-none focus:border-sky-500"
          autoFocus
        />
        <button type="submit" disabled={busy || code.length !== 6} className={primaryBtn}>
          {busy ? 'Checking...' : 'Verify code'}
        </button>
        <button type="button" onClick={() => { setChallengeId(null); setError(null) }} className="w-full text-xs text-slate-500 hover:text-sky-400 transition-colors">
          Use a different address
        </button>
      </form>
    )
  } else if (loginChallenge && method === 'email') {
    body = (
      <form onSubmit={sendCode} className="space-y-4">
        <div>
          <label htmlFor="login-email" className="block text-xs font-medium text-slate-400 mb-1.5">Email</label>
          <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus className={inputClass} />
        </div>
        <button type="submit" disabled={busy || !email} className={primaryBtn}>
          {busy ? 'Sending...' : 'Email me a code'}
        </button>
        <button type="button" onClick={() => { setMethod('choose'); setError(null) }} className="w-full text-xs text-slate-500 hover:text-sky-400 transition-colors">
          Back
        </button>
      </form>
    )
  } else if (loginChallenge) {
    body = (
      <div className="space-y-3">
        <button type="button" onClick={() => signInWithPasskey('owner')} disabled={busy} className={primaryBtn}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="7" r="4" /><path d="M5.5 21a6.5 6.5 0 0 1 13 0" /><path d="M17 11l2 2-2 2" />
          </svg>
          {busy ? 'Waiting for passkey...' : 'Sign in as owner'}
        </button>
        <p className="text-[11px] text-slate-500 text-center -mt-1">Your Squawk passkey</p>
        <button type="button" onClick={() => signInWithPasskey('account')} disabled={busy} className={secondaryBtn}>
          Use an account passkey
        </button>
        <button type="button" onClick={() => { setMethod('email'); setError(null) }} disabled={busy} className={secondaryBtn}>
          Email me a code
        </button>
      </div>
    )
  } else if (config === null) {
    body = <div className="h-12 rounded-lg bg-slate-800/60 animate-pulse" aria-hidden />
  } else if (config === 'unavailable') {
    body = (
      <p className="text-sm text-rose-400">
        The FinForge API is unreachable. Try again shortly.
      </p>
    )
  } else if (!config.enabled) {
    body = (
      <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">
        <p className="font-medium">Squawk is not configured.</p>
        <p className="mt-1 text-amber-200/80">
          FinForge signs in only through Squawk. Set <code className="font-mono text-xs">SQUAWK_ISSUER</code> and the
          other <code className="font-mono text-xs">SQUAWK_*</code> variables in the API&apos;s .env.
        </p>
      </div>
    )
  } else {
    body = (
      <div className="space-y-4">
        <button type="button" onClick={startSquawk} disabled={busy} className={primaryBtn}>
          {busy ? 'Redirecting...' : 'Sign in with Squawk'}
        </button>
        <p className="text-[11px] text-slate-500 text-center">Passkey or email code via Squawk</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          <div className="flex items-center gap-2.5 mb-1">
            <img src="/finforge_minimal.png" alt="FinForge" className="w-7 h-7 rounded-md" />
            <h1 className="text-2xl font-bold text-sky-400">FinForge</h1>
          </div>
          <p className="text-sm text-slate-400 mb-6">
            {loginChallenge ? 'Confirm it is you to continue' : 'Sign in to your account'}
          </p>

          {error && <p className="text-rose-400 text-sm mb-4" role="alert">{error}</p>}

          {body}
        </div>
        <div className="mt-4 flex justify-center gap-3 text-xs text-slate-500">
          <Link to="/privacy" className="hover:text-sky-400 transition-colors">Privacy Policy</Link>
          <span>&middot;</span>
          <Link to="/security" className="hover:text-sky-400 transition-colors">Security</Link>
        </div>
      </div>
    </div>
  )
}
