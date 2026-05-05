// FinForge TypeScript interfaces — mirrors Pydantic schemas in api/schemas/schemas.py

export interface SummaryResponse {
  net_worth: number
  savings_balance: number   // Schwab Brokerage ONLY — Roth IRA excluded per PRD
  liquid_cash: number       // WF Checking
  cc_balance_owed: number   // WF CC + Amex combined
  as_of: string             // date ISO string
}

export interface AccountBalanceResponse {
  alias: string
  account_type: 'checking' | 'credit_card' | 'brokerage' | 'ira'
  institution: string
  balance_amount: number
  balance_type: string
  balance_date: string
  last_updated: string
}

export interface CategorySpend {
  category: string
  amount: number
  pct_of_total: number
}

export interface CardSpend {
  alias: string
  amount: number
}

export interface FixedExpenses {
  rent: number
  tuition: number
  total: number
}

export interface MonthlySpendingResponse {
  month: string
  total_discretionary: number
  by_category: CategorySpend[]
  by_card: CardSpend[]
  fixed_expenses: FixedExpenses
  transaction_count: number
}

export interface TransactionResponse {
  id: string
  date: string
  amount: number
  merchant_name: string | null
  category: string | null
  subcategory: string | null
  is_pending: boolean
  is_fixed_expense: boolean
  account_alias: string
  notes: string | null
}

export interface HoldingDetail {
  symbol: string
  quantity: number
  market_value: number
  cost_basis: number | null
  unrealized_gain_loss: number | null
  pct_of_portfolio: number
}

export interface BrokerageResponse {
  total_portfolio_value: number
  cash_position: number
  invested_position: number
  holdings: HoldingDetail[]
  snapshot_date: string | null
  as_of: string | null
}

export interface IRAYearContribution {
  year: number
  amount: number
}

export interface IRAResponse {
  current_balance: number
  contributions_ytd: number
  contribution_limit: number      // $7,000 for 2026 per PRD
  contributions_remaining: number
  contribution_pct_complete: number
  growth_amount: number
  contribution_history: IRAYearContribution[]
  as_of: string | null
}

export interface InsightResponse {
  id: string
  insight_date: string
  insight_type: 'spending_pattern' | 'goal_trajectory' | 'savings_opportunity' | 'anomaly'
  content: string
  expires_at: string
  created_at: string
}

export interface InsightsResponse {
  insights: InsightResponse[]
  generated_at: string
}

export interface GoalProgressResponse {
  id: string
  name: string
  goal_type: string
  target_value: number
  target_date: string | null
  direction: string
  cadence: string
  alert_threshold: number
  natebot_enabled: boolean
  status: string
  current_value: number | null
  pct_complete: number | null
  progress_status: string   // On Track | At Risk | Off Track | Completed | No Data
  projected_completion_date: string | null
  last_snapshot_date: string | null
}

export interface GoalsListResponse {
  goals: GoalProgressResponse[]
  total: number
}

export interface GoalAlertResponse {
  id: string
  goal_id: string
  goal_name: string
  alert_type: string
  message: string
  is_acknowledged: boolean
  acknowledged_at: string | null
  created_at: string
}

export interface AlertsListResponse {
  alerts: GoalAlertResponse[]
  total: number
  unacknowledged_count: number
}

export interface GoalSnapshotItem {
  snapshot_date: string
  current_value: number
  target_value: number
  pct_complete: number
}

export interface GoalDetailResponse {
  id: string
  name: string
  goal_type: string
  metric_source: string
  target_value: number
  target_date: string | null
  direction: string
  cadence: string
  alert_threshold: number
  natebot_enabled: boolean
  status: string
  progress_status: string   // On Track | At Risk | Off Track | Completed | No Data
  current_value: number | null
  pct_complete: number | null
  projected_completion_date: string | null
  snapshots: GoalSnapshotItem[]
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error'
  version: string
  db_connected: boolean
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  message: string
  history: ChatMessage[]
}

export interface ChatResponse {
  reply: string
}

// ---------------------------------------------------------------------------
// Market Data & Watchlists
// ---------------------------------------------------------------------------

export interface MarketQuote {
  symbol: string
  last_price: number | null
  open_price: number | null
  high_price: number | null
  low_price: number | null
  close_price: number | null
  volume: number | null
  net_change: number | null
  net_change_pct: number | null
  high_52w: number | null
  low_52w: number | null
  pe_ratio: number | null
  dividend_yield: number | null
  fetched_at: string | null
}

export interface WatchlistItem {
  id: string
  symbol: string
  added_at: string
  quote: MarketQuote | null
}

export interface Watchlist {
  id: string
  name: string
  created_at: string
  updated_at: string
  items: WatchlistItem[]
}

export interface WatchlistsListResponse {
  watchlists: Watchlist[]
  total: number
}

// ---------------------------------------------------------------------------
// Goals — Create & Templates
// ---------------------------------------------------------------------------

export interface GoalTemplate {
  id: string
  name: string
  goal_type: string
  direction: string
  metric_source: string
  description: string
}

export interface GoalCreateBody {
  name: string
  goal_type: string
  metric_source: string
  target_value: number
  target_date?: string | null
  direction: string
  cadence: string
  alert_threshold?: number
  natebot_enabled?: boolean
}

// ---------------------------------------------------------------------------
// Portfolio Analysis
// ---------------------------------------------------------------------------

export interface PortfolioMetrics {
  hhi: number | null
  top5_concentration: number | null
  weighted_volatility: number | null
  max_drawdown: number | null
}

export interface SymbolAnalysis {
  symbol: string
  market_value: number | null
  cost_basis: number | null
  unrealized_gl: number | null
  pct_of_portfolio: number | null
  target_pct: number | null
  drift_pct: number | null
  annualized_vol: number | null
  beta: number | null
  drawdown_from_high: number | null
  tlh_candidate: boolean
  wash_sale_risk: boolean
  wash_sale_details: string | null
}

export interface RebalanceAction {
  symbol: string
  current_pct: number
  target_pct: number
  drift_pct: number
  action: 'BUY' | 'SELL' | 'HOLD'
  suggested_trade_value: number
}

export interface TLHCandidate {
  symbol: string
  unrealized_gl: number
  market_value: number
  cost_basis: number
  wash_sale_risk: boolean
  wash_sale_details: string | null
}

export interface PortfolioAnalysisResponse {
  analysis_date: string | null
  portfolio_metrics: PortfolioMetrics
  holdings: SymbolAnalysis[]
  rebalance_actions: RebalanceAction[]
  tlh_candidates: TLHCandidate[]
}

export interface PortfolioTargetItem {
  symbol: string
  target_pct: number
}

export interface DrawdownPrediction {
  symbol: string
  drawdown_probability: number
  risk_level: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH'
  prediction_date: string
  model_version: string
  model_auc: number | null
}

export interface PortfolioDrawdownResponse {
  predictions: DrawdownPrediction[]
  model_trained_at: string | null
  model_auc: number | null
}

export interface OptionsChainResponse {
  symbol?: string
  status?: string
  callExpDateMap?: Record<string, Record<string, OptionContract[]>>
  putExpDateMap?: Record<string, Record<string, OptionContract[]>>
}

export interface OptionContract {
  putCall: string
  symbol: string
  description: string
  bid: number
  ask: number
  last: number
  totalVolume: number
  openInterest: number
  strikePrice: number
  expirationDate: string
  daysToExpiration: number
  inTheMoney: boolean
}
