import { createContext, useContext } from 'react'

export interface AuthState {
  token: string | null
  mfaRequired: boolean
  mfaPendingToken: string | null
  login: (username: string, password: string) => Promise<void>
  verifyMfa: (code: string) => Promise<void>
  logout: () => void
  setupMfa: () => Promise<{ secret: string; qr_code: string; otpauth_uri: string }>
  confirmMfa: (code: string) => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
