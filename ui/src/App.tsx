import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import AuthProvider from './components/AuthProvider'
import { useAuth } from './hooks/useAuth'
import LoginPage from './pages/LoginPage'
import PrivacyPolicyPage from './pages/PrivacyPolicyPage'
import SecurityPolicyPage from './pages/SecurityPolicyPage'

const DashboardPage   = lazy(() => import('./pages/DashboardPage'))
const SpendingPage    = lazy(() => import('./pages/SpendingPage'))
const InvestmentsPage = lazy(() => import('./pages/InvestmentsPage'))
const GoalsPage       = lazy(() => import('./pages/GoalsPage'))
const ChatPage        = lazy(() => import('./pages/ChatPage'))
const AlertsPage      = lazy(() => import('./pages/AlertsPage'))
const MFASetupPage    = lazy(() => import('./pages/MFASetupPage'))
const SettingsPage    = lazy(() => import('./pages/SettingsPage'))
const WatchlistsPage         = lazy(() => import('./pages/WatchlistsPage'))
const PortfolioAnalysisPage  = lazy(() => import('./pages/PortfolioAnalysisPage'))
const ReimbursementPage      = lazy(() => import('./pages/ReimbursementPage'))
const ReportsPage            = lazy(() => import('./pages/ReportsPage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-slate-500 text-sm">Loading...</div>
    </div>
  )
}

function LoginRoute() {
  const { token, mfaRequired } = useAuth()

  if (token && !mfaRequired) {
    return <Navigate to="/" replace />
  }

  return <LoginPage />
}

function AuthenticatedRoutes() {
  const { token, mfaRequired } = useAuth()

  if (!token || mfaRequired) {
    return <Navigate to="/login" replace />
  }

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={
          <Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>
        } />
        <Route path="spending" element={
          <Suspense fallback={<PageLoader />}><SpendingPage /></Suspense>
        } />
        <Route path="reimbursement" element={
          <Suspense fallback={<PageLoader />}><ReimbursementPage /></Suspense>
        } />
        <Route path="reports" element={
          <Suspense fallback={<PageLoader />}><ReportsPage /></Suspense>
        } />
        <Route path="investments" element={
          <Suspense fallback={<PageLoader />}><InvestmentsPage /></Suspense>
        } />
        <Route path="goals" element={
          <Suspense fallback={<PageLoader />}><GoalsPage /></Suspense>
        } />
        <Route path="chat" element={
          <Suspense fallback={<PageLoader />}><ChatPage /></Suspense>
        } />
        <Route path="watchlists" element={
          <Suspense fallback={<PageLoader />}><WatchlistsPage /></Suspense>
        } />
        <Route path="portfolio" element={
          <Suspense fallback={<PageLoader />}><PortfolioAnalysisPage /></Suspense>
        } />
        <Route path="alerts" element={
          <Suspense fallback={<PageLoader />}><AlertsPage /></Suspense>
        } />
        <Route path="settings" element={
          <Suspense fallback={<PageLoader />}><SettingsPage /></Suspense>
        } />
        <Route path="settings/mfa" element={
          <Suspense fallback={<PageLoader />}><MFASetupPage /></Suspense>
        } />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public routes — no authentication required */}
        <Route path="/privacy" element={<PrivacyPolicyPage />} />
        <Route path="/security" element={<SecurityPolicyPage />} />
        <Route path="/login" element={<LoginRoute />} />

        {/* Everything else requires authentication */}
        <Route path="/*" element={<AuthenticatedRoutes />} />
      </Routes>
    </AuthProvider>
  )
}
