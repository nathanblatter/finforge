import type {
  SummaryResponse,
  AccountBalanceResponse,
  MonthlySpendingResponse,
  TransactionResponse,
  BrokerageResponse,
  IRAResponse,
  InsightsResponse,
  GoalsListResponse,
  GoalProgressResponse,
  GoalDetailResponse,
  AlertsListResponse,
  GoalAlertResponse,
  HealthResponse,
  ChatRequest,
  ChatResponse,
  Watchlist,
  WatchlistsListResponse,
  OptionsChainResponse,
  GoalTemplate,
  GoalCreateBody,
  PortfolioAnalysisResponse,
  PortfolioTargetItem,
  DrawdownPrediction,
  PortfolioDrawdownResponse,
} from '../types'

const API_KEY = import.meta.env.VITE_API_KEY as string
const BASE = '/api/v1'
const TOKEN_KEY = 'finforge_token'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
    ...options?.headers as Record<string, string>,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  if (res.status === 401 || res.status === 403) {
    // Token expired or MFA not verified — force re-login
    localStorage.removeItem(TOKEN_KEY)
    window.location.reload()
    throw new Error('Session expired')
  }

  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getHealth: () =>
    apiFetch<HealthResponse>('/health'),

  getSummary: () =>
    apiFetch<SummaryResponse>('/summary'),

  getBalances: async () => {
    const raw = await apiFetch<AccountBalanceResponse[]>('/balances')
    return raw.map(b => ({ ...b, balance_amount: Number(b.balance_amount) }))
  },

  getMonthlySpending: async (month?: string) => {
    const raw = await apiFetch<MonthlySpendingResponse>(
      `/spending/monthly${month ? `?month=${month}` : ''}`
    )
    // API returns Decimal fields as strings — coerce to numbers
    return {
      ...raw,
      total_discretionary: Number(raw.total_discretionary),
      by_category: raw.by_category.map(c => ({
        ...c,
        amount: Number(c.amount),
        pct_of_total: Number(c.pct_of_total),
      })),
      by_card: raw.by_card.map(c => ({
        ...c,
        amount: Number(c.amount),
      })),
      fixed_expenses: {
        rent: Number(raw.fixed_expenses.rent),
        tuition: Number(raw.fixed_expenses.tuition),
        total: Number(raw.fixed_expenses.total),
      },
    }
  },

  getTransactions: (params?: { month?: string; category?: string }) => {
    const q = new URLSearchParams()
    if (params?.month) q.set('month', params.month)
    if (params?.category) q.set('category', params.category)
    const qs = q.toString()
    return apiFetch<TransactionResponse[]>(`/spending/transactions${qs ? `?${qs}` : ''}`)
  },

  getBrokerage: () =>
    apiFetch<BrokerageResponse>('/investments/brokerage'),

  getIRA: () =>
    apiFetch<IRAResponse>('/investments/ira'),

  getInsights: () =>
    apiFetch<InsightsResponse>('/insights/latest'),

  getGoals: () =>
    apiFetch<GoalsListResponse>('/goals?status='),

  getGoal: (id: string) =>
    apiFetch<GoalDetailResponse>(`/goals/${id}`),

  getGoalTemplates: () =>
    apiFetch<{ templates: GoalTemplate[] }>('/goals/templates'),

  createGoal: (body: GoalCreateBody) =>
    apiFetch<GoalDetailResponse>('/goals', { method: 'POST', body: JSON.stringify(body) }),

  deleteGoal: (id: string) =>
    apiFetch<void>(`/goals/${id}`, { method: 'DELETE' }),

  updateGoalStatus: (id: string, goalStatus: string) =>
    apiFetch<GoalDetailResponse>(`/goals/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: goalStatus }),
    }),

  getAlerts: (includeAcknowledged = false) =>
    apiFetch<AlertsListResponse>(
      `/alerts${includeAcknowledged ? '?include_acknowledged=true' : ''}`
    ),

  acknowledgeAlert: (id: string) =>
    apiFetch<GoalAlertResponse>(`/alerts/${id}/acknowledge`, { method: 'POST' }),

  postChat: (req: ChatRequest) =>
    apiFetch<ChatResponse>('/chat', { method: 'POST', body: JSON.stringify(req) }),

  // Watchlists
  getWatchlists: () =>
    apiFetch<WatchlistsListResponse>('/watchlists'),

  getWatchlist: (id: string) =>
    apiFetch<Watchlist>(`/watchlists/${id}`),

  createWatchlist: (name: string, symbols: string[] = []) =>
    apiFetch<Watchlist>('/watchlists', {
      method: 'POST',
      body: JSON.stringify({ name, symbols }),
    }),

  renameWatchlist: (id: string, name: string) =>
    apiFetch<Watchlist>(`/watchlists/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),

  deleteWatchlist: (id: string) =>
    apiFetch<void>(`/watchlists/${id}`, { method: 'DELETE' }),

  addWatchlistSymbol: (id: string, symbol: string) =>
    apiFetch<Watchlist>(`/watchlists/${id}/symbols`, {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),

  removeWatchlistSymbol: (id: string, symbol: string) =>
    apiFetch<void>(`/watchlists/${id}/symbols/${symbol}`, { method: 'DELETE' }),

  // Options
  getOptionsChain: (symbol: string, contractType = 'ALL', strikeCount = 10) =>
    apiFetch<OptionsChainResponse>(
      `/schwab/options/${symbol}?contract_type=${contractType}&strike_count=${strikeCount}`
    ),

  // Portfolio Analysis
  getPortfolioAnalysis: () =>
    apiFetch<PortfolioAnalysisResponse>('/portfolio/analysis'),

  getPortfolioTargets: () =>
    apiFetch<{ targets: PortfolioTargetItem[] }>('/portfolio/targets'),

  setPortfolioTargets: (accountAlias: string, targets: PortfolioTargetItem[]) =>
    apiFetch<{ targets: PortfolioTargetItem[] }>('/portfolio/targets', {
      method: 'PUT',
      body: JSON.stringify({ account_alias: accountAlias, targets }),
    }),

  getDrawdownPredictions: () =>
    apiFetch<PortfolioDrawdownResponse>('/portfolio/predictions'),

  predictDrawdown: (symbol: string) =>
    apiFetch<DrawdownPrediction>('/portfolio/predict', {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),

  // Reports
  getFinancialPreview: (period: string, month: string, startDate?: string, endDate?: string) =>
    apiFetch<any>(`/reports/financial/preview?period=${period}&month=${month}${startDate ? `&start_date=${startDate}` : ''}${endDate ? `&end_date=${endDate}` : ''}`),

  getTithingIncome: (period: string, month: string, startDate?: string, endDate?: string) =>
    apiFetch<any>(`/reports/tithing/income?period=${period}&month=${month}${startDate ? `&start_date=${startDate}` : ''}${endDate ? `&end_date=${endDate}` : ''}`),

  getContributionPreview: (period: string, month: string, startDate?: string, endDate?: string) =>
    apiFetch<any>(`/reports/contributions/preview?period=${period}&month=${month}${startDate ? `&start_date=${startDate}` : ''}${endDate ? `&end_date=${endDate}` : ''}`),

  emailFinancialReport: (body: any) =>
    apiFetch<any>('/reports/financial/email', { method: 'POST', body: JSON.stringify(body) }),

  emailTithingReport: (body: any) =>
    apiFetch<any>('/reports/tithing/email', { method: 'POST', body: JSON.stringify(body) }),

  emailContributionReport: (body: any) =>
    apiFetch<any>('/reports/contributions/email', { method: 'POST', body: JSON.stringify(body) }),

  // Live quotes (existing endpoint)
  getQuotes: (symbols: string) =>
    apiFetch<{ quotes: Record<string, any> }>(`/schwab/quotes?symbols=${symbols}`),

  // Reimbursement
  getReimbursementTransactions: (month: string, rentAmount: number, miscTarget: number) =>
    apiFetch<any>(`/reimbursement/transactions?month=${month}&rent_amount=${rentAmount}&misc_target=${miscTarget}`),

  emailReimbursement: (body: { transaction_ids: string[]; rent_amount: number; month: string; verbose?: boolean }) =>
    apiFetch<{ status: string; to: string; subject: string }>('/reimbursement/email', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  exportReimbursement: async (body: { transaction_ids: string[]; rent_amount: number; month: string; verbose?: boolean }) => {
    const token = localStorage.getItem(TOKEN_KEY)
    const headers: Record<string, string> = {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
    }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${BASE}/reimbursement/export`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // Use filename from Content-Disposition header, fallback to formatted name
    const cd = res.headers.get('content-disposition')
    const match = cd?.match(/filename="?(.+?)"?$/)
    const [y, m] = body.month.split('-')
    const monthName = new Date(Number(y), Number(m) - 1).toLocaleString('en-US', { month: 'long' })
    a.download = match?.[1] || `${monthName} '${y.slice(2)} expenses.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
}
