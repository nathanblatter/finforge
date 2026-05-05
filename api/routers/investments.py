"""
GET /api/v1/investments/brokerage — Schwab Brokerage portfolio
GET /api/v1/investments/ira       — Schwab Roth IRA balance, contributions, growth
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance, Holding, Transaction
from schemas.schemas import (
    BrokerageResponse,
    HoldingDetail,
    IRAResponse,
    IRAYearContribution,
)

router = APIRouter(tags=["investments"])

MONEY_MARKET_TICKERS = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
CONTRIBUTION_LIMIT = Decimal("7000.00")   # Roth IRA limit for 2026 per PRD
INVESTMENT_TRANSFER_CATEGORY = "Investment Transfer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_account(db: Session, alias: str) -> Optional[Account]:
    return db.query(Account).filter_by(alias=alias).first()


def _latest_balance(db: Session, account_id, balance_type: str) -> Optional[Balance]:
    return (
        db.query(Balance)
        .filter_by(account_id=account_id, balance_type=balance_type)
        .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Brokerage
# ---------------------------------------------------------------------------

@router.get("/investments/brokerage", response_model=BrokerageResponse)
def get_brokerage(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> BrokerageResponse:
    """
    Schwab Individual Brokerage portfolio.
    Per PRD: treated as primary savings vehicle — total portfolio value = savings balance.
    Returns zeros on missing data (expected during initial setup).
    """
    zero = Decimal("0.00")
    today = date.today()
    account = _get_account(db, "Schwab Brokerage")

    if account is None:
        return BrokerageResponse(
            total_portfolio_value=zero, cash_position=zero, invested_position=zero,
            holdings=[], snapshot_date=None, as_of=None,
        )

    latest_bal = _latest_balance(db, account.id, "portfolio_value")
    total = Decimal(str(latest_bal.balance_amount)) if latest_bal else zero
    as_of = latest_bal.balance_date if latest_bal else None

    latest_snapshot_date = (
        db.query(func.max(Holding.snapshot_date))
        .filter_by(account_id=account.id)
        .scalar()
    )

    if latest_snapshot_date is None:
        return BrokerageResponse(
            total_portfolio_value=total, cash_position=zero, invested_position=total,
            holdings=[], snapshot_date=None, as_of=as_of,
        )

    holdings_orm = (
        db.query(Holding)
        .filter_by(account_id=account.id, snapshot_date=latest_snapshot_date)
        .order_by(Holding.market_value.desc())
        .all()
    )

    # Cash = total portfolio value minus sum of all holding market values.
    # This captures sweep funds and cash positions that aren't stored as holdings.
    holdings_total = sum(
        (Decimal(str(h.market_value)) for h in holdings_orm),
        zero,
    )
    cash = max(total - holdings_total, zero)
    invested = holdings_total

    details: list[HoldingDetail] = []
    for h in holdings_orm:
        mv = Decimal(str(h.market_value))
        cb = Decimal(str(h.cost_basis)) if h.cost_basis is not None else None
        details.append(
            HoldingDetail(
                symbol=h.symbol,
                quantity=Decimal(str(h.quantity)),
                market_value=mv,
                cost_basis=cb,
                unrealized_gain_loss=(mv - cb) if cb is not None else None,
                pct_of_portfolio=(mv / total * 100).quantize(Decimal("0.0001")) if total else zero,
            )
        )

    return BrokerageResponse(
        total_portfolio_value=total,
        cash_position=cash,
        invested_position=invested,
        holdings=details,
        snapshot_date=latest_snapshot_date,
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Roth IRA
# ---------------------------------------------------------------------------

@router.get("/investments/ira", response_model=IRAResponse)
def get_ira(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> IRAResponse:
    """
    Schwab Roth IRA.
    Per PRD: tracked separately, shown in net worth but EXCLUDED from savings balance.
    Shows contributions_ytd vs $7,000 limit, plus growth attribution.
    """
    zero = Decimal("0.00")
    today = date.today()
    account = _get_account(db, "Schwab Roth IRA")

    if account is None:
        return IRAResponse(
            current_balance=zero, contributions_ytd=zero, contribution_limit=CONTRIBUTION_LIMIT,
            contributions_remaining=CONTRIBUTION_LIMIT, contribution_pct_complete=zero,
            growth_amount=zero, contribution_history=[], as_of=None,
        )

    # Current balance
    latest_bal = _latest_balance(db, account.id, "portfolio_value") or (
        db.query(Balance).filter_by(account_id=account.id).order_by(Balance.balance_date.desc()).first()
    )
    current_balance = Decimal(str(latest_bal.balance_amount)) if latest_bal else zero
    as_of = latest_bal.balance_date if latest_bal else None

    # YTD contributions
    ytd = (
        db.query(func.sum(Transaction.amount))
        .filter(
            Transaction.account_id == account.id,
            Transaction.category == INVESTMENT_TRANSFER_CATEGORY,
            extract("year", Transaction.date) == today.year,
        )
        .scalar()
    )
    contributions_ytd = Decimal(str(ytd)) if ytd else zero

    # All-time contributions for growth attribution
    all_time = (
        db.query(func.sum(Transaction.amount))
        .filter(
            Transaction.account_id == account.id,
            Transaction.category == INVESTMENT_TRANSFER_CATEGORY,
        )
        .scalar()
    )
    total_contributions = Decimal(str(all_time)) if all_time else zero
    growth_amount = current_balance - total_contributions

    # Contribution history by year
    rows = (
        db.query(
            extract("year", Transaction.date).label("yr"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.account_id == account.id,
            Transaction.category == INVESTMENT_TRANSFER_CATEGORY,
        )
        .group_by(extract("year", Transaction.date))
        .order_by(extract("year", Transaction.date).desc())
        .all()
    )

    remaining = max(CONTRIBUTION_LIMIT - contributions_ytd, zero)
    pct = (contributions_ytd / CONTRIBUTION_LIMIT * 100).quantize(Decimal("0.01")) if CONTRIBUTION_LIMIT else zero

    return IRAResponse(
        current_balance=current_balance,
        contributions_ytd=contributions_ytd,
        contribution_limit=CONTRIBUTION_LIMIT,
        contributions_remaining=remaining,
        contribution_pct_complete=pct,
        growth_amount=growth_amount,
        contribution_history=[IRAYearContribution(year=int(r.yr), amount=Decimal(str(r.total))) for r in rows],
        as_of=as_of,
    )
