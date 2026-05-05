"""
GET /api/v1/spending/monthly  — discretionary CC spend breakdown for a month
GET /api/v1/spending/transactions — filterable transaction feed
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Transaction
from schemas.schemas import (
    CardSpend,
    CategorySpend,
    FixedExpenses,
    MonthlySpendingResponse,
    TransactionResponse,
)

router = APIRouter(tags=["spending"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_bounds(month_str: str) -> tuple[date, date]:
    """Parse YYYY-MM → (first_day, last_day)."""
    try:
        year, mon = int(month_str[:4]), int(month_str[5:7])
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format '{month_str}'. Expected YYYY-MM.",
        )
    first_day = date(year, mon, 1)
    if mon == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, mon + 1, 1) - timedelta(days=1)
    return first_day, last_day


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Monthly spending
# ---------------------------------------------------------------------------

@router.get("/spending/monthly", response_model=MonthlySpendingResponse)
def get_monthly_spending(
    month: str = Query(default=None, description="YYYY-MM — defaults to current month"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> MonthlySpendingResponse:
    """
    Discretionary CC spend for the month, broken down by category and card.
    Fixed expenses (rent, tuition) shown separately and excluded from discretionary total.
    Per PRD: CC spend pool = WF Credit Card + Amex Credit Card combined.
    """
    if month is None:
        month = _current_month()
    first_day, last_day = _month_bounds(month)

    cc_accounts = (
        db.query(Account)
        .filter(Account.account_type == "credit_card")
        .all()
    )
    cc_ids = [a.id for a in cc_accounts]
    alias_map: dict[uuid.UUID, str] = {a.id: a.alias for a in cc_accounts}

    # Discretionary = CC transactions, not fixed, not pending, within month
    discretionary = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(cc_ids),
            Transaction.is_fixed_expense == False,
            Transaction.is_pending == False,
            Transaction.date >= first_day,
            Transaction.date <= last_day,
        )
        .all()
    )

    total = sum(Decimal(str(t.amount)) for t in discretionary)

    # By category
    cat_totals: dict[str, Decimal] = {}
    for t in discretionary:
        cat = t.category or "Other"
        cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + Decimal(str(t.amount))

    by_category = [
        CategorySpend(
            category=cat,
            amount=amt,
            pct_of_total=(amt / total * 100).quantize(Decimal("0.01")) if total else Decimal("0"),
        )
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # By card (WF Credit Card and Amex separately per PRD)
    card_totals: dict[str, Decimal] = {}
    for t in discretionary:
        alias = alias_map.get(t.account_id, "Unknown")
        card_totals[alias] = card_totals.get(alias, Decimal("0")) + Decimal(str(t.amount))

    by_card = [CardSpend(alias=a, amount=v) for a, v in sorted(card_totals.items())]

    # Fixed expenses (from ALL accounts, not just CC)
    fixed_txns = (
        db.query(Transaction)
        .filter(
            Transaction.is_fixed_expense == True,
            Transaction.date >= first_day,
            Transaction.date <= last_day,
        )
        .all()
    )
    rent = Decimal("0")
    tuition = Decimal("0")
    for t in fixed_txns:
        cat = (t.category or "").strip().lower()
        amt = Decimal(str(t.amount))
        if cat == "housing":
            rent += amt
        elif cat == "education":
            tuition += amt

    return MonthlySpendingResponse(
        month=month,
        total_discretionary=total,
        by_category=by_category,
        by_card=by_card,
        fixed_expenses=FixedExpenses(rent=rent, tuition=tuition, total=rent + tuition),
        transaction_count=len(discretionary),
    )


# ---------------------------------------------------------------------------
# Transaction feed
# ---------------------------------------------------------------------------

@router.get("/spending/transactions", response_model=list[TransactionResponse])
def get_transactions(
    days: int = Query(default=30, ge=1, description="Last N days"),
    category: str | None = Query(default=None, description="Filter by FinForge category"),
    account_alias: str | None = Query(default=None, description="Filter by account alias"),
    include_pending: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> list[TransactionResponse]:
    """
    Filterable transaction feed across all accounts.
    account_alias returned in response — account_id and plaid_transaction_id never exposed.
    """
    since = date.today() - timedelta(days=days)

    q = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Transaction.date >= since)
    )
    if not include_pending:
        q = q.filter(Transaction.is_pending == False)
    if category:
        q = q.filter(Transaction.category == category)
    if account_alias:
        q = q.filter(Account.alias == account_alias)

    rows = q.order_by(Transaction.date.desc()).limit(limit).all()

    return [
        TransactionResponse(
            id=t.id,
            date=t.date,
            amount=Decimal(str(t.amount)),
            merchant_name=t.merchant_name,
            category=t.category,
            subcategory=t.subcategory,
            is_pending=t.is_pending,
            is_fixed_expense=t.is_fixed_expense,
            account_alias=a.alias,
            notes=t.notes,
        )
        for t, a in rows
    ]
