"""SQLAlchemy ORM models for FinForge.

All models use SQLAlchemy 2.0 style with Mapped[] type annotations.
UUIDs are generated at the application level for portability across DB engines.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------------------------------------------------------------------
# Enum definitions
# ---------------------------------------------------------------------------

AccountTypeEnum = Enum(
    "checking",
    "credit_card",
    "brokerage",
    "ira",
    name="account_type_enum",
)

BalanceTypeEnum = Enum(
    "cash",
    "portfolio_value",
    name="balance_type_enum",
)

GoalTypeEnum = Enum(
    "balance_target",
    "contribution_rate",
    "spend_limit",
    "portfolio_growth",
    "custom",
    name="goal_type_enum",
)

GoalDirectionEnum = Enum(
    "increase",
    "decrease",
    "maintain",
    name="goal_direction_enum",
)

GoalCadenceEnum = Enum(
    "daily",
    "weekly",
    "monthly",
    name="goal_cadence_enum",
)

GoalStatusEnum = Enum(
    "active",
    "paused",
    "completed",
    "failed",
    name="goal_status_enum",
)

InsightTypeEnum = Enum(
    "spending_pattern",
    "goal_trajectory",
    "savings_opportunity",
    "anomaly",
    name="insight_type_enum",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    """An authenticated FinForge user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User username={self.username!r}>"


class Account(Base):
    """A financial account tracked by FinForge."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    account_type: Mapped[str] = mapped_column(AccountTypeEnum, nullable=False)
    institution: Mapped[str] = mapped_column(String(150), nullable=False)
    last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )
    balances: Mapped[list["Balance"]] = relationship(
        "Balance", back_populates="account", cascade="all, delete-orphan"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Account alias={self.alias!r} type={self.account_type!r}>"


class Transaction(Base):
    """An individual financial transaction."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("plaid_transaction_id", name="uq_transaction_plaid_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plaid_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    merchant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fixed_expense: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction date={self.date!r} amount={self.amount!r} "
            f"merchant={self.merchant_name!r}>"
        )


class Balance(Base):
    """A point-in-time account balance snapshot."""

    __tablename__ = "balances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    balance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_type: Mapped[str] = mapped_column(BalanceTypeEnum, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="balances")

    def __repr__(self) -> str:
        return (
            f"<Balance account_id={self.account_id!r} "
            f"date={self.balance_date!r} amount={self.balance_amount!r}>"
        )


class Holding(Base):
    """A brokerage/IRA holding snapshot."""

    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="holdings")

    def __repr__(self) -> str:
        return (
            f"<Holding symbol={self.symbol!r} "
            f"date={self.snapshot_date!r} value={self.market_value!r}>"
        )


class Goal(Base):
    """A financial goal tracked over time."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_type: Mapped[str] = mapped_column(GoalTypeEnum, nullable=False)
    # JSON string encoding the account aliases and/or categories this goal monitors
    metric_source: Mapped[str] = mapped_column(Text, nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    direction: Mapped[str] = mapped_column(GoalDirectionEnum, nullable=False)
    cadence: Mapped[str] = mapped_column(GoalCadenceEnum, nullable=False)
    alert_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("10.0")
    )
    natebot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        GoalStatusEnum, nullable=False, default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    snapshots: Mapped[list["GoalSnapshot"]] = relationship(
        "GoalSnapshot", back_populates="goal", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["GoalAlert"]] = relationship(
        "GoalAlert", back_populates="goal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Goal name={self.name!r} type={self.goal_type!r} status={self.status!r}>"


class GoalSnapshot(Base):
    """A point-in-time progress snapshot for a goal."""

    __tablename__ = "goal_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    current_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pct_complete: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="snapshots")

    def __repr__(self) -> str:
        return (
            f"<GoalSnapshot goal_id={self.goal_id!r} "
            f"date={self.snapshot_date!r} pct={self.pct_complete!r}>"
        )


class ClaudeInsight(Base):
    """An AI-generated insight produced by the Claude integration."""

    __tablename__ = "claude_insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    insight_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    insight_type: Mapped[str] = mapped_column(InsightTypeEnum, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ClaudeInsight type={self.insight_type!r} "
            f"date={self.insight_date!r}>"
        )


class GoalAlert(Base):
    """An alert triggered when a goal crosses its alert_threshold."""

    __tablename__ = "goal_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # off_track, at_risk, completed
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    goal: Mapped["Goal"] = relationship("Goal")

    def __repr__(self) -> str:
        return f"<GoalAlert goal_id={self.goal_id!r} type={self.alert_type!r} ack={self.is_acknowledged!r}>"


class NatebotEvent(Base):
    """An audit record of an outbound NateBot notification event."""

    __tablename__ = "natebot_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<NatebotEvent type={self.event_type!r} "
            f"timestamp={self.timestamp!r}>"
        )


class Watchlist(Base):
    """A user-scoped watchlist of ticker symbols."""

    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    items: Mapped[list["WatchlistItem"]] = relationship(
        "WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Watchlist name={self.name!r} user_id={self.user_id!r}>"


class WatchlistItem(Base):
    """A symbol in a watchlist."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    watchlist: Mapped["Watchlist"] = relationship("Watchlist", back_populates="items")

    def __repr__(self) -> str:
        return f"<WatchlistItem symbol={self.symbol!r} watchlist_id={self.watchlist_id!r}>"


class MarketDataCache(Base):
    """Cached latest quote per symbol, refreshed by cron."""

    __tablename__ = "market_data_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    last_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    net_change: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    net_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    high_52w: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    low_52w: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    dividend_yield: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MarketDataCache symbol={self.symbol!r} last_price={self.last_price!r}>"


class CronLog(Base):
    """Persisted cron job log entries for the log viewer."""

    __tablename__ = "cron_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<CronLog job={self.job_name!r} level={self.level!r}>"


class PortfolioTarget(Base):
    """User-defined target allocation per symbol for rebalancing."""

    __tablename__ = "portfolio_targets"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_portfolio_target_acct_sym"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<PortfolioTarget symbol={self.symbol!r} target_pct={self.target_pct!r}>"


class PortfolioAnalysis(Base):
    """Cron-computed portfolio risk, rebalancing, and TLH analysis per symbol."""

    __tablename__ = "portfolio_analysis"
    __table_args__ = (
        UniqueConstraint("account_id", "analysis_date", "symbol", name="uq_portfolio_analysis"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    cost_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    unrealized_gl: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    pct_of_portfolio: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    target_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    drift_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    annualized_vol: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    drawdown_from_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    tlh_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wash_sale_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wash_sale_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Portfolio-level metrics (only on __PORTFOLIO__ sentinel row)
    hhi: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    top5_concentration: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    weighted_volatility: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<PortfolioAnalysis symbol={self.symbol!r} date={self.analysis_date!r}>"


class DrawdownPrediction(Base):
    """Cached ML drawdown prediction per symbol."""

    __tablename__ = "drawdown_predictions"
    __table_args__ = (
        UniqueConstraint("symbol", "prediction_date", name="uq_drawdown_pred_sym_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    drawdown_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<DrawdownPrediction symbol={self.symbol!r} prob={self.drawdown_probability!r}>"


class NatebotQueue(Base):
    """Queued iMessage notifications for NateBot to poll and deliver."""

    __tablename__ = "natebot_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<NatebotQueue cat={self.category!r} delivered={self.delivered!r}>"
