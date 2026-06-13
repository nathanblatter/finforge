import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import MobileNav from './MobileNav'
import DownloadQueue from './DownloadQueue'
import ErrorBoundary from '../ErrorBoundary'
import CommandPalette from '../CommandPalette'
import { DownloadQueueProvider } from '../../hooks/useDownloadQueue'
import { PrivacyProvider, PrivacyScope } from '../../hooks/usePrivacy'

export default function Layout() {
  return (
    <PrivacyProvider>
      <DownloadQueueProvider>
        <PrivacyScope>
          <div className="flex h-screen bg-slate-900">
            <Sidebar />
            <main className="flex-1 overflow-y-auto p-4 pb-24 md:p-6">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
            <MobileNav />
            <DownloadQueue />
            <CommandPalette />
          </div>
        </PrivacyScope>
      </DownloadQueueProvider>
    </PrivacyProvider>
  )
}
