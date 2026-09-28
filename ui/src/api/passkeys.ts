/**
 * Passkey (WebAuthn) client. Talks to /auth/passkeys/* and drives the browser
 * credential ceremony via @simplewebauthn/browser.
 */
import {
  startAuthentication,
  startRegistration,
  browserSupportsWebAuthn,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'

interface OptionsResponse<T> {
  options: T
  challenge_token: string
}

export interface TokenResponse {
  access_token: string
  mfa_required: boolean
}

export interface PasskeyInfo {
  id: string
  name: string
  created_at: string
  last_used_at: string | null
  backed_up: boolean
}

async function call<T>(path: string, method: string, body?: object, token?: string | null): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'X-API-Key': API_KEY }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Error ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const passkeysSupported = browserSupportsWebAuthn

/** Register a new passkey. `token` is a session token or a magic-link enrollment token. */
export async function registerPasskey(token: string, name: string): Promise<TokenResponse> {
  const { options, challenge_token } = await call<OptionsResponse<PublicKeyCredentialCreationOptionsJSON>>(
    '/auth/passkeys/register/options', 'POST', {}, token,
  )
  const credential = await startRegistration({ optionsJSON: options })
  return call<TokenResponse>(
    '/auth/passkeys/register/verify', 'POST', { credential, challenge_token, name }, token,
  )
}

/** Sign in with a passkey. Username is optional (discoverable credentials). */
export async function loginWithPasskey(username?: string): Promise<TokenResponse> {
  const { options, challenge_token } = await call<OptionsResponse<PublicKeyCredentialRequestOptionsJSON>>(
    '/auth/passkeys/login/options', 'POST', { username: username || null },
  )
  const credential = await startAuthentication({ optionsJSON: options })
  return call<TokenResponse>('/auth/passkeys/login/verify', 'POST', { credential, challenge_token })
}

export function listPasskeys(token: string): Promise<PasskeyInfo[]> {
  return call<PasskeyInfo[]>('/auth/passkeys', 'GET', undefined, token)
}

export function deletePasskey(token: string, id: string): Promise<{ status: string }> {
  return call('/auth/passkeys/' + id, 'DELETE', undefined, token)
}

/** Friendly default name from the current browser/platform. */
export function defaultPasskeyName(): string {
  const ua = navigator.userAgent
  const platform = /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : /Mac/.test(ua) ? 'Mac'
    : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : 'Device'
  const browser = /Safari/.test(ua) && !/Chrome/.test(ua) ? 'Safari' : /Chrome/.test(ua) ? 'Chrome' : /Firefox/.test(ua) ? 'Firefox' : ''
  return [platform, browser].filter(Boolean).join(' ')
}
