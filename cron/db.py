"""
SQLAlchemy engine, session factory, and ORM models for the FinForge cron service.

The cron container does not share code with the api container, so it defines
its own lightweight ORM models that mirror the shared Postgres schema.
"""

import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Generator, Optional

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
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from config import settings

# ---------------------------------------------------------------------------
# Engine & session
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM models — mirror api/models/db_models.py schema exactly
# ---------------------------------------------------------------------------

class AccountRow(Base):
    __tablename__ = "accounts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    account_type: Mapped[str] = mapped_column(
        Enum("checking", "credit_card", "brokerage", "ira", name="account_type_enum"),
        nullable=False,
    )
    institution: Mapped[str] = mapped_column(String(150), nullable=False)
    last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TransactionRow(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("plaid_transaction_id", name="uq_transaction_plaid_id"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    plaid_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    merchant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fixed_expense: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class BalanceRow(Base):
    __tablename__ = "balances"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    balance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_type: Mapped[str] = mapped_column(
        Enum("cash", "portfolio_value", name="balance_type_enum"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HoldingRow(Base):
    __tablename__ = "holdings"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GoalRow(Base):
    __tablename__ = "goals"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_type: Mapped[str] = mapped_column(
        Enum(
            "balance_target", "contribution_rate", "spend_limit",
            "portfolio_growth", "custom",
            name="goal_type_enum",
        ),
        nullable=False,
    )
    metric_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    direction: Mapped[str] = mapped_column(
        Enum("increase", "decrease", "maintain", name="goal_direction_enum"),
        nullable=False,
    )
    cadence: Mapped[str] = mapped_column(
        Enum("daily", "weekly", "monthly", name="goal_cadence_enum"),
        nullable=False,
    )
    alert_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("10.0"))
    natebot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        Enum("active", "paused", "completed", "failed", name="goal_status_enum"),
        nullable=False,
        default="active",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class GoalSnapshotRow(Base):
    __tablename__ = "goal_snapshots"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    current_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pct_complete: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GoalAlertRow(Base):
    __tablename__ = "goal_alerts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ClaudeInsightRow(Base):
    __tablename__ = "claude_insights"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insight_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WatchlistItemRow(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketDataCacheRow(Base):
    __tablename__ = "market_data_cache"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PortfolioTargetRow(Base):
    __tablename__ = "portfolio_targets"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_portfolio_target_acct_sym"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PortfolioAnalysisRow(Base):
    __tablename__ = "portfolio_analysis"
    __table_args__ = (
        UniqueConstraint("account_id", "analysis_date", "symbol", name="uq_portfolio_analysis"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)
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
    hhi: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    top5_concentration: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    weighted_volatility: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    max_drawdown: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NatebotQueueRow(Base):
    __tablename__ = "natebot_queue"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DrawdownPredictionRow(Base):
    __tablename__ = "drawdown_predictions"
    __table_args__ = (
        UniqueConstraint("symbol", "prediction_date", name="uq_drawdown_pred_sym_date"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)
    drawdown_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CronLogRow(Base):
    __tablename__ = "cron_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# Session context manager
# ---------------------------------------------------------------------------

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a DB session. Commits on success, rolls back on exception."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def get_or_create_account(
    session: Session,
    alias: str,
    account_type: str,
    institution: str,
    last4: Optional[str] = None,
) -> uuid.UUID:
    """
    Look up an account by alias. Create it if it doesn't exist.
    Returns the internal UUID (never an institution account number).
    """
    row = session.query(AccountRow).filter_by(alias=alias).first()
    if row is None:
        row = AccountRow(
            id=uuid.uuid4(),
            alias=alias,
            account_type=account_type,
            institution=institution,
            last4=last4,
            is_active=True,
        )
        session.add(row)
        session.flush()
    return row.id
