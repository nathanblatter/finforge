import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import DownloadQueue from './DownloadQueue'
import ErrorBoundary from '../ErrorBoundary'
import { DownloadQueueProvider } from '../../hooks/useDownloadQueue'

export default function Layout() {
  return (
    <DownloadQueueProvider>
      <div className="flex h-screen bg-slate-900">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
        <DownloadQueue />
      </div>
    </DownloadQueueProvider>
  )
}
