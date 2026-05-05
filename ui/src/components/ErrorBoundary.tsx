import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex items-center justify-center min-h-[400px] p-6">
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 max-w-md w-full text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-rose-500/10 mb-4">
              <svg className="w-6 h-6 text-rose-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-slate-100 mb-2">Something went wrong</h2>
            <p className="text-sm text-slate-500 mb-6">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <div className="flex items-center justify-center gap-3">
              <button onClick={this.handleReset}
                className="px-4 py-2 text-sm font-medium rounded-md bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors">
                Try Again
              </button>
              <button onClick={() => window.location.reload()}
                className="px-4 py-2 text-sm font-medium rounded-md bg-rose-600 text-white hover:bg-rose-500 transition-colors">
                Reload
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
