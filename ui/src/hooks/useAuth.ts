import { createContext, useContext } from 'react'

export interface AuthState {
  token: string | null
  /** Install a FinForge session token obtained from the Squawk code exchange. */
  setSession: (accessToken: string) => void
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
