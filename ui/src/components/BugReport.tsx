import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

type Status = 'idle' | 'sending' | 'sent' | 'error'

const SEVERITIES = [
  { value: 'low', label: 'Minor — a small annoyance' },
  { value: 'med', label: 'Medium — gets in the way' },
  { value: 'high', label: 'High — hard to use' },
  { value: 'urgent', label: 'Urgent — completely broken' },
]

function BugIcon({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M8 9a4 4 0 0 1 8 0v4a4 4 0 0 1-8 0V9Z" />
      <path d="M12 5V3M9 6 7.5 4.5M15 6l1.5-1.5M5 11H3M21 11h-2M5.5 16 4 17.5M18.5 16l1.5 1.5M12 13v6" />
    </svg>
  )
}

export default function BugReport() {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [severity, setSeverity] = useState('med')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    const id = window.setTimeout(() => textareaRef.current?.focus(), 40)
    return () => {
      document.removeEventListener('keydown', onKey)
      window.clearTimeout(id)
    }
  }, [open])

  function close() {
    setOpen(false)
    // Reset shortly after the modal unmounts so the next open is clean.
    window.setTimeout(() => {
      setMessage('')
      setSeverity('med')
      setStatus('idle')
      setError('')
    }, 200)
  }

  async function send() {
    const trimmed = message.trim()
    if (!trimmed) {
      setError('Add a quick description first.')
      textareaRef.current?.focus()
      return
    }
    setStatus('sending')
    setError('')
    try {
      await api.submitBugReport({
        message: trimmed,
        severity,
        url: window.location.href,
        meta: {
          path: window.location.pathname,
          viewport: `${window.innerWidth}x${window.innerHeight}`,
          userAgent: navigator.userAgent,
        },
      })
      setStatus('sent')
      window.setTimeout(close, 1300)
    } catch {
      setStatus('error')
      setError('Could not send. Please try again.')
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Report a bug"
        className="fixed bottom-20 right-4 z-40 flex items-center gap-2 rounded-full bg-sky-500 px-4 py-3
                   text-sm font-semibold text-white shadow-lg shadow-sky-500/25 transition
                   hover:-translate-y-0.5 hover:bg-sky-400 focus:outline-none focus-visible:ring-2
                   focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900
                   md:bottom-6 md:right-6"
      >
        <BugIcon className="h-4 w-4" />
        <span className="hidden sm:inline">Report a bug</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) close()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Report a bug"
            className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-2xl
                       motion-safe:animate-[toast-in_.2s_ease-out]"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 text-sky-400">
                <BugIcon className="h-5 w-5" />
              </span>
              <div>
                <h2 className="text-lg font-semibold text-slate-100">Spotted a bug?</h2>
                <p className="mt-0.5 text-sm text-slate-400">
                  Tell us what happened — it goes straight to the board.
                </p>
              </div>
            </div>

            {status === 'sent' ? (
              <div className="mt-6 flex items-center gap-2 rounded-lg bg-emerald-500/10 px-4 py-6 text-emerald-400">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden="true">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
                <span className="text-sm font-medium">Thanks — your report was filed.</span>
              </div>
            ) : (
              <>
                <label htmlFor="bug-message" className="mt-5 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                  What went wrong?
                </label>
                <textarea
                  id="bug-message"
                  ref={textareaRef}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Describe what you saw, and what you expected…"
                  rows={4}
                  maxLength={5000}
                  className="mt-2 w-full resize-y rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm
                             text-slate-100 placeholder-slate-500 focus:border-sky-500 focus:outline-none
                             focus:ring-2 focus:ring-sky-500/30"
                />

                <label htmlFor="bug-severity" className="mt-4 block text-xs font-semibold uppercase tracking-wide text-slate-400">
                  How bad is it?
                </label>
                <select
                  id="bug-severity"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 p-2.5 text-sm
                             text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/30"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>

                <div className="mt-5 flex items-center gap-3">
                  <span className="mr-auto text-xs text-rose-400">{error}</span>
                  <button
                    type="button"
                    onClick={close}
                    className="text-sm font-medium text-slate-400 transition hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={send}
                    disabled={status === 'sending'}
                    className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white transition
                               hover:bg-sky-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300
                               disabled:cursor-default disabled:opacity-60"
                  >
                    {status === 'sending' ? 'Sending…' : 'Send report'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
