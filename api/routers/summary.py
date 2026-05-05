"""GET /api/v1/summary — financial state snapshot for NateBot morning briefing."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance
from schemas.schemas import SummaryResponse

router = APIRouter(tags=["summary"])

_ACCOUNT_ALIASES = [
    "WF Checking",
    "WF Credit Card",
    "Amex Credit Card",
    "Schwab Brokerage",
    "Schwab Roth IRA",
]


def _latest_balance(db: Session, alias: str) -> Decimal:
    """Return most recent balance for an account alias, or 0 if not found."""
    account = db.query(Account).filter_by(alias=alias).first()
    if account is None:
        return Decimal("0")
    balance = (
        db.query(Balance)
        .filter_by(account_id=account.id)
        .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
        .first()
    )
    return Decimal(str(balance.balance_amount)) if balance else Decimal("0")


def _latest_balance_date(db: Session, alias: str) -> date | None:
    account = db.query(Account).filter_by(alias=alias).first()
    if account is None:
        return None
    balance = (
        db.query(Balance)
        .filter_by(account_id=account.id)
        .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
        .first()
    )
    return balance.balance_date if balance else None


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> SummaryResponse:
    """
    Current financial state snapshot.

    Net Worth = WF Checking + Schwab Brokerage + Schwab Roth IRA − (WF CC + Amex)
    Savings Balance = Schwab Brokerage ONLY (Roth IRA is excluded per PRD)
    """
    wf_checking = _latest_balance(db, "WF Checking")
    schwab_brokerage = _latest_balance(db, "Schwab Brokerage")
    schwab_roth = _latest_balance(db, "Schwab Roth IRA")
    wf_cc = _latest_balance(db, "WF Credit Card")
    amex = _latest_balance(db, "Amex Credit Card")

    net_worth = wf_checking + schwab_brokerage + schwab_roth - wf_cc - amex
    savings_balance = schwab_brokerage   # Roth IRA intentionally excluded
    liquid_cash = wf_checking
    cc_balance_owed = wf_cc + amex

    dates = [_latest_balance_date(db, a) for a in _ACCOUNT_ALIASES]
    valid_dates = [d for d in dates if d is not None]
    if not valid_dates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No balance data available. Run a sync first.",
        )

    return SummaryResponse(
        net_worth=net_worth,
        savings_balance=savings_balance,
        liquid_cash=liquid_cash,
        cc_balance_owed=cc_balance_owed,
        as_of=max(valid_dates),
    )
