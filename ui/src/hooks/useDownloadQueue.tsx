import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from 'react'

export interface DownloadJob {
  id: string
  name: string
  status: 'pending' | 'ready' | 'error'
  url?: string
  error?: string
  justCompleted?: boolean
}

interface DownloadQueueContextValue {
  jobs: DownloadJob[]
  addJob: (name: string, fetchFn: () => Promise<Blob>) => void
  dismissJob: (id: string) => void
}

const DownloadQueueContext = createContext<DownloadQueueContextValue | null>(null)

let jobCounter = 0

export function DownloadQueueProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs

  const addJob = useCallback((name: string, fetchFn: () => Promise<Blob>) => {
    const id = `dl-${++jobCounter}-${Date.now()}`
    const job: DownloadJob = { id, name, status: 'pending' }

    setJobs(prev => [...prev, job])

    fetchFn()
      .then(blob => {
        const url = URL.createObjectURL(blob)
        setJobs(prev =>
          prev.map(j => j.id === id ? { ...j, status: 'ready' as const, url, justCompleted: true } : j)
        )
        // Clear the justCompleted flag after a brief highlight period
        setTimeout(() => {
          setJobs(prev =>
            prev.map(j => j.id === id ? { ...j, justCompleted: false } : j)
          )
        }, 3000)
      })
      .catch(err => {
        setJobs(prev =>
          prev.map(j =>
            j.id === id
              ? { ...j, status: 'error' as const, error: err instanceof Error ? err.message : 'Download failed' }
              : j
          )
        )
      })
  }, [])

  const dismissJob = useCallback((id: string) => {
    setJobs(prev => {
      const job = prev.find(j => j.id === id)
      if (job?.url) URL.revokeObjectURL(job.url)
      return prev.filter(j => j.id !== id)
    })
  }, [])

  return (
    <DownloadQueueContext.Provider value={{ jobs, addJob, dismissJob }}>
      {children}
    </DownloadQueueContext.Provider>
  )
}

export function useDownloadQueue(): DownloadQueueContextValue {
  const ctx = useContext(DownloadQueueContext)
  if (!ctx) throw new Error('useDownloadQueue must be used within DownloadQueueProvider')
  return ctx
}
