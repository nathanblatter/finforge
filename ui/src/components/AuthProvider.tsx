import { useState, useCallback, useMemo, type ReactNode } from 'react'
import { AuthContext, type AuthState } from '../hooks/useAuth'

const TOKEN_KEY = 'finforge_token'

/**
 * Holds the FinForge session token (a bearer JWT in localStorage). Sign-in
 * happens through Squawk; LoginCallbackPage installs the token via setSession.
 */
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))

  const setSession = useCallback((accessToken: string) => {
    localStorage.setItem(TOKEN_KEY, accessToken)
    setToken(accessToken)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
  }, [])

  const value: AuthState = useMemo(() => ({ token, setSession, logout }), [token, setSession, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
