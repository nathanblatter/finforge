"""Pydantic response schemas for FinForge.

All schemas use model_config = ConfigDict(from_attributes=True) so they can be
constructed directly from SQLAlchemy ORM instances.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

class AccountSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alias: str
    account_type: Literal["checking", "credit_card", "brokerage", "ira"]
    institution: str
    last4: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

class TransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    plaid_transaction_id: Optional[str]
    date: date
    amount: Decimal
    merchant_name: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    is_pending: bool
    is_fixed_expense: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

class BalanceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    balance_date: date
    balance_amount: Decimal
    balance_type: Literal["cash", "portfolio_value"]
    created_at: datetime


# ---------------------------------------------------------------------------
# Holding
# ---------------------------------------------------------------------------

class HoldingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    snapshot_date: date
    symbol: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Optional[Decimal]
    created_at: datetime


# ---------------------------------------------------------------------------
# Goal
# ---------------------------------------------------------------------------

class GoalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    goal_type: Literal[
        "balance_target",
        "contribution_rate",
        "spend_limit",
        "portfolio_growth",
        "custom",
    ]
    metric_source: str
    target_value: Decimal
    target_date: Optional[date]
    direction: Literal["increase", "decrease", "maintain"]
    cadence: Literal["daily", "weekly", "monthly"]
    alert_threshold: Decimal
    natebot_enabled: bool
    status: Literal["active", "paused", "completed", "failed"]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# GoalSnapshot
# ---------------------------------------------------------------------------

class GoalSnapshotSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    goal_id: uuid.UUID
    snapshot_date: date
    current_value: Decimal
    target_value: Decimal
    pct_complete: Decimal
    created_at: datetime


# ---------------------------------------------------------------------------
# ClaudeInsight
# ---------------------------------------------------------------------------

class ClaudeInsightSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    insight_date: date
    insight_type: Literal[
        "spending_pattern",
        "goal_trajectory",
        "savings_opportunity",
        "anomaly",
    ]
    content: str
    expires_at: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# NatebotEvent
# ---------------------------------------------------------------------------

class NatebotEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    event_type: str
    payload_hash: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response schema for the /api/v1/health endpoint."""

    model_config = ConfigDict(from_attributes=False)

    status: Literal["ok", "degraded", "error"]
    version: str
    environment: str
    db_connected: bool
    last_plaid_sync: Optional[datetime]
    last_schwab_sync: Optional[datetime]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    net_worth: Decimal
    savings_balance: Decimal    # Schwab Brokerage only — Roth IRA excluded per PRD
    liquid_cash: Decimal        # WF Checking
    cc_balance_owed: Decimal    # WF CC + Amex combined
    as_of: date


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------

class AccountBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    alias: str
    account_type: str
    institution: str
    balance_amount: Decimal
    balance_type: str
    balance_date: date
    last_updated: date


# ---------------------------------------------------------------------------
# Spending
# ---------------------------------------------------------------------------

class CategorySpend(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    category: str
    amount: Decimal
    pct_of_total: Decimal


class CardSpend(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    alias: str
    amount: Decimal


class FixedExpenses(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    rent: Decimal
    tuition: Decimal
    total: Decimal


class MonthlySpendingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    month: str
    total_discretionary: Decimal
    by_category: list[CategorySpend]
    by_card: list[CardSpend]
    fixed_expenses: FixedExpenses
    transaction_count: int


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    id: uuid.UUID
    date: date
    amount: Decimal
    merchant_name: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    is_pending: bool
    is_fixed_expense: bool
    account_alias: str      # never account_id — joined from accounts table
    notes: Optional[str]


# ---------------------------------------------------------------------------
# Investments — Brokerage
# ---------------------------------------------------------------------------

class HoldingDetail(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Optional[Decimal]
    unrealized_gain_loss: Optional[Decimal]
    pct_of_portfolio: Decimal


class BrokerageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    total_portfolio_value: Decimal
    cash_position: Decimal
    invested_position: Decimal
    holdings: list[HoldingDetail]
    snapshot_date: Optional[date]
    as_of: Optional[date]


# ---------------------------------------------------------------------------
# Investments — Roth IRA
# ---------------------------------------------------------------------------

class IRAYearContribution(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    year: int
    amount: Decimal


class IRAResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    current_balance: Decimal
    contributions_ytd: Decimal
    contribution_limit: Decimal     # $7,000 for 2026 per PRD
    contributions_remaining: Decimal
    contribution_pct_complete: Decimal
    growth_amount: Decimal
    contribution_history: list[IRAYearContribution]
    as_of: Optional[date]


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

class InsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    insight_date: date
    insight_type: str
    content: str
    expires_at: datetime
    created_at: datetime


class InsightsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    insights: list[InsightResponse]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Goal progress (used by goals router)
# ---------------------------------------------------------------------------

class GoalSnapshotItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_date: date
    current_value: Decimal
    target_value: Decimal
    pct_complete: Decimal


class GoalProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    id: uuid.UUID
    name: str
    goal_type: str
    target_value: Decimal
    target_date: Optional[date]
    direction: str
    cadence: str
    alert_threshold: Decimal
    natebot_enabled: bool
    status: str
    current_value: Optional[Decimal]
    pct_complete: Optional[Decimal]
    progress_status: str
    projected_completion_date: Optional[date]
    last_snapshot_date: Optional[date]


class GoalsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    goals: list[GoalProgressResponse]
    total: int


class GoalDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    id: uuid.UUID
    name: str
    goal_type: str
    metric_source: str
    target_value: Decimal
    target_date: Optional[date]
    direction: str
    cadence: str
    alert_threshold: Decimal
    natebot_enabled: bool
    status: str
    progress_status: str
    current_value: Optional[Decimal]
    pct_complete: Optional[Decimal]
    projected_completion_date: Optional[date]
    snapshots: list[GoalSnapshotItem]


# ---------------------------------------------------------------------------
# Goal CRUD request schemas
# ---------------------------------------------------------------------------

class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    name: str
    goal_type: Literal[
        "balance_target", "contribution_rate", "spend_limit", "portfolio_growth", "custom"
    ]
    metric_source: str      # JSON string — account aliases or category names only, never credentials
    target_value: Decimal
    target_date: Optional[date] = None
    direction: Literal["increase", "decrease", "maintain"]
    cadence: Literal["daily", "weekly", "monthly"]
    alert_threshold: Decimal = Decimal("10.0")
    natebot_enabled: bool = False


class GoalUpdateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    name: Optional[str] = None
    target_value: Optional[Decimal] = None
    target_date: Optional[date] = None
    alert_threshold: Optional[Decimal] = None
    natebot_enabled: Optional[bool] = None
    metric_source: Optional[str] = None


class GoalStatusPatch(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    status: Literal["active", "paused", "completed", "failed"]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class GoalAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    id: uuid.UUID
    goal_id: uuid.UUID
    goal_name: str
    alert_type: str
    message: str
    is_acknowledged: bool
    acknowledged_at: Optional[datetime]
    created_at: datetime


class AlertsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    alerts: list[GoalAlertResponse]
    total: int
    unacknowledged_count: int


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# NateBot
# ---------------------------------------------------------------------------

class NatebotGoalSummary(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    name: str
    pct_complete: Optional[Decimal]
    progress_status: str
    target_value: Decimal
    current_value: Optional[Decimal]


class NatebotBriefingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    net_worth: Decimal
    savings_balance: Decimal
    liquid_cash: Decimal
    cc_balance_owed: Decimal
    goals: list[NatebotGoalSummary]
    unacknowledged_alerts: int
    latest_insight: Optional[str]
    as_of: date


class WeeklySpendingComparison(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    this_week_total: Decimal
    last_week_total: Decimal
    change_amount: Decimal
    change_pct: Optional[Decimal]
    this_week_top_categories: list[CategorySpend]
    period_start: date
    period_end: date


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    message: str
    history: list[ChatMessage] = []   # session history from frontend, not persisted


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    reply: str


# ---------------------------------------------------------------------------
# Market Data Cache
# ---------------------------------------------------------------------------

class MarketQuote(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    last_price: Optional[Decimal] = None
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    volume: Optional[int] = None
    net_change: Optional[Decimal] = None
    net_change_pct: Optional[Decimal] = None
    high_52w: Optional[Decimal] = None
    low_52w: Optional[Decimal] = None
    pe_ratio: Optional[Decimal] = None
    dividend_yield: Optional[Decimal] = None
    fetched_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------

class WatchlistItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    symbol: str
    added_at: datetime
    quote: Optional[MarketQuote] = None


class WatchlistSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    items: list[WatchlistItemSchema] = []


class WatchlistCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    name: str
    symbols: list[str] = []


class WatchlistRenameRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    name: str


class WatchlistAddSymbolRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str


class WatchlistsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    watchlists: list[WatchlistSchema]
    total: int


# ---------------------------------------------------------------------------
# Portfolio Analysis
# ---------------------------------------------------------------------------

class SymbolAnalysis(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str
    market_value: Optional[Decimal] = None
    cost_basis: Optional[Decimal] = None
    unrealized_gl: Optional[Decimal] = None
    pct_of_portfolio: Optional[Decimal] = None
    target_pct: Optional[Decimal] = None
    drift_pct: Optional[Decimal] = None
    annualized_vol: Optional[Decimal] = None
    beta: Optional[Decimal] = None
    drawdown_from_high: Optional[Decimal] = None
    tlh_candidate: bool = False
    wash_sale_risk: bool = False
    wash_sale_details: Optional[str] = None


class PortfolioMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    hhi: Optional[Decimal] = None
    top5_concentration: Optional[Decimal] = None
    weighted_volatility: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None


class RebalanceAction(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str
    current_pct: Decimal
    target_pct: Decimal
    drift_pct: Decimal
    action: str
    suggested_trade_value: Decimal


class TLHCandidate(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str
    unrealized_gl: Decimal
    market_value: Decimal
    cost_basis: Decimal
    wash_sale_risk: bool
    wash_sale_details: Optional[str] = None


class PortfolioAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    analysis_date: Optional[date] = None
    portfolio_metrics: PortfolioMetrics
    holdings: list[SymbolAnalysis]
    rebalance_actions: list[RebalanceAction]
    tlh_candidates: list[TLHCandidate]


class PortfolioTargetItem(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str
    target_pct: Decimal


class PortfolioTargetsRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    account_alias: str
    targets: list[PortfolioTargetItem]


# ---------------------------------------------------------------------------
# Drawdown Predictions
# ---------------------------------------------------------------------------

class DrawdownPredictionRequest(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    symbol: str


class DrawdownPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False, protected_namespaces=())
    symbol: str
    drawdown_probability: Decimal
    risk_level: str
    prediction_date: date
    model_version: str
    model_auc: Optional[Decimal] = None


class PortfolioDrawdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False, protected_namespaces=())
    predictions: list[DrawdownPredictionResponse]
    model_trained_at: Optional[str] = None
    model_auc: Optional[Decimal] = None
