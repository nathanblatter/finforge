import type {
  SummaryResponse,
  AccountBalanceResponse,
  MonthlySpendingResponse,
  TransactionResponse,
  BrokerageResponse,
  IRAResponse,
  InsightsResponse,
  CategoryRule,
  CategoryRulesResponse,
  SubscriptionsResponse,
  GoalsListResponse,
  GoalProgressResponse,
  GoalDetailResponse,
  AlertsListResponse,
  GoalAlertResponse,
  HealthResponse,
  ChatRequest,
  ChatResponse,
  ChatHistoryResponse,
  Watchlist,
  WatchlistsListResponse,
  OptionsChainResponse,
  GoalTemplate,
  GoalCreateBody,
  PortfolioAnalysisResponse,
  PortfolioTargetItem,
  DrawdownPrediction,
  PortfolioDrawdownResponse,
  DrawdownFavoritesResponse,
  BudgetItem,
  BudgetsListResponse,
  PriceAlertItem,
  PriceAlertsListResponse,
  DividendIncomeSummaryResponse,
  DividendCalendarResponse,
  DividendHistoryResponse,
  FrontierResponse,
  ClustersResponse,
  IvHvResponse,
  MonteCarloRequest,
  MonteCarloResponse,
  SpendingForecastResponse,
  SpendingAnomaliesResponse,
  RegimeResponse,
  CoveredCallsResponse,
  BenchmarkResponse,
  SectorsResponse,
  DailySpendingResponse,
  MoneyFlowResponse,
  StreaksResponse,
  WrappedResponse,
  SearchResponse,
  MerchantDetailResponse,
  BillsForecastResponse,
  RunwayResponse,
  CashflowSettingsResponse,
  WhatIfResponse,
  TaxSummaryResponse,
  RealizedLotsResponse,
  TaxEstimateResponse,
  TaxEstimateSettings,
  Form1099Response,
  FireSettings,
  FireSettingsUpdate,
  FireSummaryResponse,
  FireMonteCarloRequest,
  FireMonteCarloResponse,
  SwrRequest,
  SwrResponse,
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

async function downloadCsv(path: string, fallbackName: string): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers: Record<string, string> = { 'X-API-Key': API_KEY }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { headers })
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cd = res.headers.get('content-disposition')
  const match = cd?.match(/filename="?(.+?)"?$/)
  a.download = match?.[1] || fallbackName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const api = {
  getHealth: () =>
    apiFetch<HealthResponse>('/health'),

  submitBugReport: (body: {
    message: string
    severity: string
    url?: string
    meta?: Record<string, unknown>
  }) =>
    apiFetch<{ ok: boolean }>('/bug-report', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

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

  updateTransactionCategory: (id: string, category: string) =>
    apiFetch<TransactionResponse>(`/spending/transactions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ category }),
    }),

  updateTransactionMeta: (id: string, meta: { notes?: string; tags?: string[] }) =>
    apiFetch<TransactionResponse>(`/spending/transactions/${id}/meta`, {
      method: 'PATCH',
      body: JSON.stringify(meta),
    }),

  getCategoryRules: () =>
    apiFetch<CategoryRulesResponse>('/spending/rules'),

  createCategoryRule: (merchant: string, category: string) =>
    apiFetch<CategoryRule>('/spending/rules', {
      method: 'POST',
      body: JSON.stringify({ merchant, category }),
    }),

  deleteCategoryRule: (id: string) =>
    apiFetch<void>(`/spending/rules/${id}`, { method: 'DELETE' }),

  getSubscriptions: async (months = 6): Promise<SubscriptionsResponse> => {
    const raw = await apiFetch<SubscriptionsResponse>(`/spending/subscriptions?months=${months}`)
    return {
      monthly_total: Number(raw.monthly_total),
      subscriptions: raw.subscriptions.map((s) => ({
        ...s,
        monthly_amount: Number(s.monthly_amount),
        avg_amount: Number(s.avg_amount),
      })),
    }
  },

  getInsightsHistory: (limit = 50) =>
    apiFetch<InsightsResponse>(`/insights/history?limit=${limit}`),

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

  getChatHistory: () =>
    apiFetch<ChatHistoryResponse>('/chat/history'),

  clearChatHistory: () =>
    apiFetch<void>('/chat/history', { method: 'DELETE' }),

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

  getDrawdownFavorites: () =>
    apiFetch<DrawdownFavoritesResponse>('/portfolio/favorites'),

  // Budgets (API returns Decimal fields as strings — coerce to numbers)
  getBudgets: async (): Promise<BudgetsListResponse> => {
    const raw = await apiFetch<BudgetsListResponse>('/budgets')
    return {
      ...raw,
      budgets: raw.budgets.map((b) => ({
        ...b,
        monthly_limit: Number(b.monthly_limit),
        spent: Number(b.spent),
        pct: Number(b.pct),
      })),
    }
  },

  upsertBudget: async (category: string, monthlyLimit: number): Promise<BudgetItem> => {
    const b = await apiFetch<BudgetItem>('/budgets', {
      method: 'PUT',
      body: JSON.stringify({ category, monthly_limit: monthlyLimit }),
    })
    return { ...b, monthly_limit: Number(b.monthly_limit), spent: Number(b.spent), pct: Number(b.pct) }
  },

  deleteBudget: (category: string) =>
    apiFetch<void>(`/budgets/${encodeURIComponent(category)}`, { method: 'DELETE' }),

  // Price alerts
  getPriceAlerts: async (): Promise<PriceAlertsListResponse> => {
    const raw = await apiFetch<PriceAlertsListResponse>('/price-alerts')
    return {
      alerts: raw.alerts.map((a) => ({
        ...a,
        threshold: Number(a.threshold),
        last_price: a.last_price == null ? null : Number(a.last_price),
      })),
    }
  },

  createPriceAlert: (symbol: string, direction: 'above' | 'below', threshold: number) =>
    apiFetch<PriceAlertItem>('/price-alerts', {
      method: 'POST',
      body: JSON.stringify({ symbol, direction, threshold }),
    }),

  deletePriceAlert: (id: string) =>
    apiFetch<void>(`/price-alerts/${id}`, { method: 'DELETE' }),

  // Dividends & income calendar
  getDividendIncome: async (): Promise<DividendIncomeSummaryResponse> => {
    const raw = await apiFetch<DividendIncomeSummaryResponse>('/dividends/income')
    return {
      ...raw,
      portfolio_projected_annual_income: Number(raw.portfolio_projected_annual_income),
      portfolio_yield_on_cost_pct: raw.portfolio_yield_on_cost_pct == null ? null : Number(raw.portfolio_yield_on_cost_pct),
      portfolio_cumulative_reinvested: Number(raw.portfolio_cumulative_reinvested),
      portfolio_cumulative_cash_received: Number(raw.portfolio_cumulative_cash_received),
      holdings: raw.holdings.map((h) => ({
        ...h,
        quantity: Number(h.quantity),
        per_share_amount: h.per_share_amount == null ? null : Number(h.per_share_amount),
        projected_annual_income: Number(h.projected_annual_income),
        yield_on_cost_pct: h.yield_on_cost_pct == null ? null : Number(h.yield_on_cost_pct),
        cost_basis: h.cost_basis == null ? null : Number(h.cost_basis),
        cumulative_reinvested: Number(h.cumulative_reinvested),
        cumulative_cash_received: Number(h.cumulative_cash_received),
      })),
    }
  },

  getDividendCalendar: async (months = 3): Promise<DividendCalendarResponse> => {
    const raw = await apiFetch<DividendCalendarResponse>(`/dividends/calendar?months=${months}`)
    return {
      ...raw,
      payments: raw.payments.map((p) => ({
        ...p,
        expected_amount: Number(p.expected_amount),
        per_share_amount: p.per_share_amount == null ? null : Number(p.per_share_amount),
        quantity: Number(p.quantity),
      })),
    }
  },

  getDividendHistory: async (symbol?: string): Promise<DividendHistoryResponse> => {
    const qs = symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''
    const raw = await apiFetch<DividendHistoryResponse>(`/dividends/history${qs}`)
    return {
      transactions: raw.transactions.map((t) => ({
        ...t,
        amount: Number(t.amount),
        quantity_at_payment: t.quantity_at_payment == null ? null : Number(t.quantity_at_payment),
        per_share_amount: t.per_share_amount == null ? null : Number(t.per_share_amount),
        reinvest_amount: t.reinvest_amount == null ? null : Number(t.reinvest_amount),
      })),
    }
  },

  addDrawdownFavorite: (symbol: string) =>
    apiFetch<DrawdownFavoritesResponse>('/portfolio/favorites', {
      method: 'POST',
      body: JSON.stringify({ symbol }),
    }),

  removeDrawdownFavorite: (symbol: string) =>
    apiFetch<void>(`/portfolio/favorites/${symbol}`, { method: 'DELETE' }),

  // Spending intelligence
  getSpendingForecast: () =>
    apiFetch<SpendingForecastResponse>('/spending/forecast'),

  getSpendingAnomalies: (includeDismissed = false) =>
    apiFetch<SpendingAnomaliesResponse>(
      `/spending/anomalies${includeDismissed ? '?include_dismissed=true' : ''}`
    ),

  dismissAnomaly: (id: string) =>
    apiFetch<void>(`/spending/anomalies/${id}/dismiss`, { method: 'POST' }),

  // Quant analytics
  getFrontier: () =>
    apiFetch<FrontierResponse>('/quant/frontier'),

  getClusters: (threshold = 0.65) =>
    apiFetch<ClustersResponse>(`/quant/clusters?threshold=${threshold}`),

  getIvHv: (symbols?: string) =>
    apiFetch<IvHvResponse>(`/quant/iv-hv${symbols ? `?symbols=${symbols}` : ''}`),

  runMonteCarlo: (body: MonteCarloRequest) =>
    apiFetch<MonteCarloResponse>('/quant/montecarlo', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getRegime: () =>
    apiFetch<RegimeResponse>('/quant/regime'),

  getCoveredCalls: () =>
    apiFetch<CoveredCallsResponse>('/quant/covered-calls'),

  getBenchmark: (days = 365) =>
    apiFetch<BenchmarkResponse>(`/quant/benchmark?days=${days}`),

  getSectors: () =>
    apiFetch<SectorsResponse>('/quant/sectors'),

  // FIRE / retirement projector
  getFireSettings: () =>
    apiFetch<FireSettings>('/fire/settings'),

  updateFireSettings: (body: FireSettingsUpdate) =>
    apiFetch<FireSettings>('/fire/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  getFireSummary: () =>
    apiFetch<FireSummaryResponse>('/fire/summary'),

  runFireMonteCarlo: (body: FireMonteCarloRequest = {}) =>
    apiFetch<FireMonteCarloResponse>('/fire/montecarlo', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  runFireSwr: (body: SwrRequest = {}) =>
    apiFetch<SwrResponse>('/fire/swr', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getDailySpending: (months = 6) =>
    apiFetch<DailySpendingResponse>(`/spending/daily?months=${months}`),

  getMoneyFlow: (month?: string) =>
    apiFetch<MoneyFlowResponse>(`/spending/flow${month ? `?month=${month}` : ''}`),

  getStreaks: () =>
    apiFetch<StreaksResponse>('/spending/streaks'),

  searchSpending: (q: string) =>
    apiFetch<SearchResponse>(`/spending/search?q=${encodeURIComponent(q)}`),

  getMerchantDetail: (name: string) =>
    apiFetch<MerchantDetailResponse>(`/spending/merchant?name=${encodeURIComponent(name)}`),

  getBillsForecast: (days = 30) =>
    apiFetch<BillsForecastResponse>(`/spending/bills-forecast?days=${days}`),

  getRunway: (days = 90) =>
    apiFetch<RunwayResponse>(`/cashflow/runway?days=${days}`),

  getCashflowSettings: () =>
    apiFetch<CashflowSettingsResponse>('/cashflow/settings'),

  updateCashflowSettings: (floorAmount: number, leadTimeDays: number) =>
    apiFetch<CashflowSettingsResponse>('/cashflow/settings', {
      method: 'PUT',
      body: JSON.stringify({ floor_amount: floorAmount, lead_time_days: leadTimeDays }),
    }),

  runWhatIf: (weights: Record<string, number>) =>
    apiFetch<WhatIfResponse>('/quant/whatif', {
      method: 'POST',
      body: JSON.stringify({ weights }),
    }),

  getWrapped: (year?: number, regenerate = false) => {
    const q = new URLSearchParams()
    if (year) q.set('year', String(year))
    if (regenerate) q.set('regenerate', 'true')
    const qs = q.toString()
    return apiFetch<WrappedResponse>(`/reports/wrapped${qs ? `?${qs}` : ''}`)
  },

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

  getTaxSummary: (marginalRate?: number) =>
    apiFetch<TaxSummaryResponse>(
      `/tax/summary${marginalRate != null ? `?marginal_rate=${marginalRate}` : ''}`,
    ),

  exportTaxHoldings: async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    const headers: Record<string, string> = { 'X-API-Key': API_KEY }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${BASE}/tax/holdings.csv`, { headers })
    if (!res.ok) throw new Error(`Export failed: ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const cd = res.headers.get('content-disposition')
    const match = cd?.match(/filename="?(.+?)"?$/)
    a.download = match?.[1] || `finforge_holdings_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },

  getRealizedLots: () =>
    apiFetch<RealizedLotsResponse>('/tax/lots'),

  getTaxEstimates: (settings: TaxEstimateSettings) => {
    const params = new URLSearchParams({
      prior_year_tax: String(settings.prior_year_tax),
      prior_year_agi: String(settings.prior_year_agi),
      filing_status: settings.filing_status,
      marginal_rate: String(settings.marginal_rate),
      ltcg_rate: String(settings.ltcg_rate),
      set_aside: String(settings.set_aside),
    })
    return apiFetch<TaxEstimateResponse>(`/tax/estimates?${params}`)
  },

  getForm1099: () =>
    apiFetch<Form1099Response>('/tax/form1099'),

  exportTaxRealized: () =>
    downloadCsv('/tax/realized.csv', `finforge_realized_${new Date().getFullYear()}.csv`),

  exportForm1099: () =>
    downloadCsv('/tax/form1099.csv', `finforge_1099_reconciliation_${new Date().getFullYear()}.csv`),
}
