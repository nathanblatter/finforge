import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { setPrivacyMode } from '../utils/format'

const STORAGE_KEY = 'finforge:privacy'

const PrivacyContext = createContext<{ enabled: boolean; toggle: () => void }>({
  enabled: false,
  toggle: () => {},
})

export function PrivacyProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(() => {
    const on = localStorage.getItem(STORAGE_KEY) === '1'
    setPrivacyMode(on)
    return on
  })

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev
      setPrivacyMode(next)
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
      return next
    })
  }, [])

  // Shift+P anywhere outside a text field
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'P' || !e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return
      e.preventDefault()
      toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  return <PrivacyContext.Provider value={{ enabled, toggle }}>{children}</PrivacyContext.Provider>
}

export function usePrivacy() {
  return useContext(PrivacyContext)
}

/** Remounts its subtree when privacy flips so every formatted string re-renders. */
export function PrivacyScope({ children }: { children: ReactNode }) {
  const { enabled } = usePrivacy()
  return (
    <div key={enabled ? 'private' : 'plain'} className="contents">
      {children}
    </div>
  )
}
