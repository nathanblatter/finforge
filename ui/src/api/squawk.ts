/**
 * Squawk sign-in client. Talks to /auth/squawk/* on the FinForge API (which
 * proxies the ceremonies to Squawk with its service token) and holds the
 * browser side of the OAuth 2.1 + PKCE dance.
 */

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'
const PKCE_KEY = 'finforge_squawk_pkce'

export interface SquawkConfig {
  enabled: boolean
  issuer: string
  client_id: string
  resource: string
  redirect_uri: string
  scope: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  mfa_required: boolean
}

/** A non-2xx answer from the API, carrying Squawk's error code when it has one. */
export class SquawkAuthError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'SquawkAuthError'
    this.status = status
    this.code = code
  }
}

async function call<T>(path: string, method: 'GET' | 'POST', body?: object): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err?.detail
    if (detail && typeof detail === 'object') {
      throw new SquawkAuthError(res.status, String(detail.error ?? 'error'), String(detail.message ?? 'Sign-in failed.'))
    }
    throw new SquawkAuthError(res.status, 'error', typeof detail === 'string' ? detail : `Error ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const squawkApi = {
  config: () => call<SquawkConfig>('/auth/squawk/config', 'GET'),
  ownerBegin: (login_challenge: string) =>
    call<{ challenge_id: string; options: { publicKey: PublicKeyCredentialRequestOptionsJSON } }>('/auth/squawk/owner/begin', 'POST', { login_challenge }),
  ownerFinish: (challenge_id: string, credential: unknown) =>
    call<{ redirect_to: string }>('/auth/squawk/owner/finish', 'POST', { challenge_id, credential }),
  passkeyBegin: (login_challenge: string) =>
    call<{ challenge_id: string; options: { publicKey: PublicKeyCredentialRequestOptionsJSON } }>('/auth/squawk/passkey/begin', 'POST', { login_challenge }),
  passkeyFinish: (challenge_id: string, credential: unknown) =>
    call<{ redirect_to: string }>('/auth/squawk/passkey/finish', 'POST', { challenge_id, credential }),
  emailBegin: (login_challenge: string, email: string) =>
    call<{ challenge_id: string; expires_in: number }>('/auth/squawk/email/begin', 'POST', { login_challenge, email }),
  emailFinish: (challenge_id: string, code: string) =>
    call<{ redirect_to: string }>('/auth/squawk/email/finish', 'POST', { challenge_id, code }),
  exchange: (code: string, code_verifier: string) =>
    call<TokenResponse>('/auth/squawk/exchange', 'POST', { code, code_verifier }),
}

// ── PKCE (RFC 7636), done in the browser; the verifier is sent to our API once with the code ──

function base64url(bytes: Uint8Array): string {
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomToken(bytes: number): string {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)))
}

async function sha256(input: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input)))
}

/** Build the /oauth/authorize URL and stash {verifier, state} for the callback. */
export async function startAuthorization(config: SquawkConfig): Promise<string> {
  const verifier = randomToken(48) // 64 chars, within RFC 7636's 43–128
  const state = randomToken(24)
  const challenge = base64url(await sha256(verifier))
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, state }))
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.client_id,
    redirect_uri: config.redirect_uri,
    state,
    resource: config.resource,
    scope: config.scope,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  })
  return `${config.issuer}/oauth/authorize?${params.toString()}`
}

/** The stashed PKCE pair, if this browser started an authorization. */
export function takeStashedPkce(): { verifier: string; state: string } | null {
  try {
    const raw = sessionStorage.getItem(PKCE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.verifier !== 'string' || typeof parsed?.state !== 'string') return null
    return parsed
  } catch {
    return null
  }
}

export function clearStashedPkce(): void {
  sessionStorage.removeItem(PKCE_KEY)
}
