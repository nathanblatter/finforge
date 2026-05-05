import { useState, useCallback, useMemo, type ReactNode } from 'react'
import { AuthContext, type AuthState } from '../hooks/useAuth'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'

async function authFetch<T>(path: string, body: object, token?: string | null): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Error ${res.status}`)
  }
  return res.json() as Promise<T>
}

const TOKEN_KEY = 'finforge_token'

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [mfaRequired, setMfaRequired] = useState(false)
  const [mfaPendingToken, setMfaPendingToken] = useState<string | null>(null)

  const login = useCallback(async (username: string, password: string) => {
    const data = await authFetch<{ access_token: string; mfa_required: boolean }>(
      '/auth/login',
      { username, password },
    )
    if (data.mfa_required) {
      setMfaRequired(true)
      setMfaPendingToken(data.access_token)
    } else {
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setMfaRequired(false)
      setMfaPendingToken(null)
    }
  }, [])

  const verifyMfa = useCallback(async (code: string) => {
    const data = await authFetch<{ access_token: string }>(
      '/auth/mfa/verify',
      { code },
      mfaPendingToken,
    )
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
    setMfaRequired(false)
    setMfaPendingToken(null)
  }, [mfaPendingToken])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setMfaRequired(false)
    setMfaPendingToken(null)
  }, [])

  const setupMfa = useCallback(async () => {
    return authFetch<{ secret: string; qr_code: string; otpauth_uri: string }>(
      '/auth/mfa/setup',
      {},
      token,
    )
  }, [token])

  const confirmMfa = useCallback(async (code: string) => {
    await authFetch<{ status: string }>('/auth/mfa/confirm', { code }, token)
  }, [token])

  const value: AuthState = useMemo(
    () => ({ token, mfaRequired, mfaPendingToken, login, verifyMfa, logout, setupMfa, confirmMfa }),
    [token, mfaRequired, mfaPendingToken, login, verifyMfa, logout, setupMfa, confirmMfa],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
