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
  category_overridden: boolean
  account_alias: string
  notes: string | null
  tags: string[]
}

export interface CategoryRule {
  id: string
  merchant: string
  category: string
  created_at: string
}

export interface CategoryRulesResponse {
  rules: CategoryRule[]
}

export interface SubscriptionItem {
  merchant: string
  category: string | null
  monthly_amount: number
  avg_amount: number
  occurrences: number
  months_seen: number
  last_date: string
}

export interface SubscriptionsResponse {
  subscriptions: SubscriptionItem[]
  monthly_total: number
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
  source: string          // 'goal' | 'budget' | 'price'
  title: string
  goal_id: string | null
  goal_name: string | null
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

// Budgets
export interface BudgetItem {
  category: string
  monthly_limit: number
  spent: number
  pct: number
  status: 'ok' | 'warning' | 'over'
}

export interface BudgetsListResponse {
  budgets: BudgetItem[]
  month: string
}

// Price alerts
export interface PriceAlertItem {
  id: string
  symbol: string
  direction: 'above' | 'below'
  threshold: number
  is_active: boolean
  last_triggered_at: string | null
  created_at: string
  last_price: number | null
}

export interface PriceAlertsListResponse {
  alerts: PriceAlertItem[]
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

export interface ChatHistoryItem {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatHistoryResponse {
  messages: ChatHistoryItem[]
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

export interface DrawdownFavoriteItem {
  symbol: string
  created_at: string
}

export interface DrawdownFavoritesResponse {
  favorites: DrawdownFavoriteItem[]
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

// ---------------------------------------------------------------------------
// Quant analytics
// ---------------------------------------------------------------------------

export interface FrontierPoint {
  vol: number
  ret: number
  sharpe: number
}

export interface FrontierPortfolio extends FrontierPoint {
  weights: Record<string, number>
}

export interface FrontierResponse {
  symbols: string[]
  cloud: FrontierPoint[]
  max_sharpe: FrontierPortfolio
  min_variance: FrontierPortfolio
  current: FrontierPoint | null
  risk_free_rate: number
  per_symbol: { symbol: string; exp_return: number; volatility: number; current_weight: number }[]
  lookback_days: number
}

export interface CorrelationCluster {
  symbols: string[]
  weight_pct: number
  avg_internal_correlation: number
}

export interface ClustersResponse {
  n_positions: number
  n_clusters: number
  corr_threshold: number
  clusters: CorrelationCluster[]
  correlation_matrix: { symbols: string[]; values: number[][] }
}

export interface IvHvItem {
  symbol: string
  hv_30d: number | null
  iv_30d: number | null
  iv_hv_ratio: number | null
  signal: 'RICH' | 'CHEAP' | 'FAIR' | 'UNKNOWN'
}

export interface IvHvResponse {
  results: IvHvItem[]
}

export interface MonteCarloRequest {
  initial_value?: number
  monthly_contribution: number
  years: number
  target_value?: number
  n_sims?: number
}

export interface MonteCarloYear {
  year: number
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
}

export interface MonteCarloResponse {
  initial_value: number
  monthly_contribution: number
  years: number
  n_sims: number
  yearly: MonteCarloYear[]
  final_median: number | null
  target_value?: number
  prob_hit_at_horizon?: number
  prob_hit_ever?: number
}

export interface ForecastCategory {
  category: string
  forecast: number
  lo: number
  hi: number
  mtd_spent: number
  mtd_projected: number
  trailing_avg: number
  history: { month: string; amount: number }[]
}

export interface SpendingForecastResponse {
  forecast_month: string
  current_month: string
  total_forecast: number
  categories: ForecastCategory[]
}

export interface SpendingAnomalyItem {
  id: string
  transaction_id: string
  reason: 'outlier' | 'duplicate'
  z_score: number | null
  typical_amount: number | null
  detail: string | null
  is_dismissed: boolean
  created_at: string
  date: string
  amount: number
  merchant_name: string | null
  category: string | null
  account_alias: string
}

export interface SpendingAnomaliesResponse {
  anomalies: SpendingAnomalyItem[]
}

export type ChargeGuardianKind = 'duplicate_charge' | 'new_subscription' | 'trial_conversion' | 'gray_charge_creep'
export type ChargeGuardianStatus = 'open' | 'dismissed' | 'legit'

export interface ChargeGuardianEvidenceTxn {
  id: string
  date: string
  amount: number
  merchant_name: string | null
  account_id: string
}

export interface ChargeGuardianFindingItem {
  id: string
  kind: ChargeGuardianKind
  merchant: string
  title: string
  detail: string
  amount: number | null
  status: ChargeGuardianStatus
  created_at: string
  evidence_transactions: ChargeGuardianEvidenceTxn[]
}

export interface ChargeGuardianFindingsResponse {
  findings: ChargeGuardianFindingItem[]
}

export interface RegimeSnapshot {
  date: string
  regime: 'bull_quiet' | 'bull_volatile' | 'bear_quiet' | 'bear_volatile' | 'choppy'
  realized_vol_20d: number | null
  trend_60d: number | null
  sma20_vs_sma50: number | null
}

export interface RegimeResponse {
  current: RegimeSnapshot | null
  history: RegimeSnapshot[]
}

// ---------------------------------------------------------------------------
// Wave 7/8: spending viz, wrapped, covered calls, benchmark, sectors
// ---------------------------------------------------------------------------

export interface DailySpendingResponse {
  start: string
  days: { date: string; total: number; count: number }[]
}

export interface MoneyFlowResponse {
  month: string
  income: number
  outflows: number
  nodes: { name: string }[]
  links: { source: number; target: number; value: number }[]
}

export interface StreaksResponse {
  has_budgets: boolean
  daily_budget: number
  current_under_budget_streak: number
  longest_streak_90d: number
  no_spend_days_this_month: number
  no_spend_days_90d: number
}

export interface WrappedResponse {
  stats: {
    year: number
    total_spend: number
    transaction_count: number
    top_categories: [string, number][]
    top_merchants_by_total: [string, number][]
    top_merchants_by_visits: [string, number][]
    biggest_month: [string, number] | null
    largest_purchase: [string, number, string] | null
    net_worth_start: number
    net_worth_end: number
    net_worth_change: number
    best_holding: [string, number] | null
    worst_holding: [string, number] | null
  }
  narrative: string | null
  partial_year: boolean
  cached: boolean
}

export interface CoveredCall {
  strike: number
  expiration_days: number
  delta: number
  premium: number
  bid: number
  ask: number
  description: string | null
  underlying_price: number
  yield_pct: number
  annualized_yield_pct: number
}

export interface CoveredCallEntry {
  symbol: string
  shares: number
  contracts_available: number
  call: CoveredCall | null
  est_monthly_income: number | null
  est_annual_income: number | null
}

export interface CoveredCallsResponse {
  as_of: string
  results: CoveredCallEntry[]
}

export interface BenchmarkResponse {
  series: { date: string; portfolio: number; spy: number }[]
  portfolio_return_pct: number
  spy_return_pct: number
  excess_return_pct: number
  n_snapshots: number
  start: string
  end: string
}

export interface SectorsResponse {
  as_of: string
  total_value: number
  sectors: { sector: string; value: number; pct: number }[]
  unclassified_pct: number
  holdings: { symbol: string; market_value: number; classification: string }[]
}

// ---------------------------------------------------------------------------
// Wave 9: search, merchant drill-down, bill forecast, what-if rebalancer
// ---------------------------------------------------------------------------

export interface SearchMerchant {
  merchant: string
  count: number
  total: number
  last_date: string
}

export interface SearchTransaction {
  id: string
  date: string
  amount: number
  merchant_name: string | null
  category: string | null
  account_alias: string
  is_pending: boolean
}

export interface SearchResponse {
  merchants: SearchMerchant[]
  transactions: SearchTransaction[]
}

export interface MerchantDetailResponse {
  merchant: string
  category: string | null
  has_rule: boolean
  total_spent: number
  visits: number
  avg_amount: number
  first_seen: string
  last_seen: string
  is_recurring: boolean
  monthly_median: number | null
  accounts: string[]
  trend: { month: string; total: number; count: number }[]
  recent: { id: string; date: string; amount: number; category: string | null; account_alias: string }[]
}

export interface BillEvent {
  date: string
  merchant: string
  amount: number
  kind: 'bill' | 'income'
  category: string | null
  cadence_days: number
  balance_after: number | null
}

export interface BillsForecastResponse {
  as_of: string
  days: number
  checking_balance: number | null
  events: BillEvent[]
  projected_low: { date: string; balance: number } | null
  projected_end_balance: number | null
}

export interface WhatIfPoint {
  ret: number
  vol: number
  sharpe: number
}

export interface WhatIfResponse {
  symbols: string[]
  whatif: WhatIfPoint & { weights: Record<string, number> }
  current: WhatIfPoint | null
}

// Tax Center
export interface TLHOpportunity {
  symbol: string
  market_value: number
  cost_basis: number
  unrealized_loss: number
  est_tax_benefit: number
  wash_sale_risk: boolean
  wash_sale_details: string | null
}

export interface RealizedActivityItem {
  symbol: string
  proceeds: number
  txn_count: number
}

export interface TaxSummaryResponse {
  analysis_date: string | null
  tax_year: number
  marginal_rate: number
  net_unrealized_gl: number
  gross_unrealized_gains: number
  gross_unrealized_losses: number
  harvestable_loss: number
  est_tax_savings: number
  tlh_opportunities: TLHOpportunity[]
  wash_sale_warnings: number
  realized_ytd_proceeds: number
  realized_ytd_sells: number
  realized_activity: RealizedActivityItem[]
  realized_is_partial: boolean
}
