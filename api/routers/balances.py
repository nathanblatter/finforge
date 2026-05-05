"""GET /api/v1/balances — current balance per account (alias only, no account numbers)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance
from schemas.schemas import AccountBalanceResponse

router = APIRouter(tags=["balances"])


@router.get("/balances", response_model=list[AccountBalanceResponse])
def get_balances(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> list[AccountBalanceResponse]:
    """
    Current balance for every active account.
    Returns alias, institution, and balance only — no account numbers or UUIDs.
    """
    accounts = db.query(Account).filter_by(is_active=True).all()

    results: list[AccountBalanceResponse] = []
    for account in accounts:
        latest = (
            db.query(Balance)
            .filter_by(account_id=account.id)
            .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
            .first()
        )
        if latest is None:
            continue

        results.append(
            AccountBalanceResponse(
                alias=account.alias,
                account_type=account.account_type,
                institution=account.institution,
                balance_amount=latest.balance_amount,
                balance_type=latest.balance_type,
                balance_date=latest.balance_date,
                last_updated=latest.balance_date,
            )
        )

    results.sort(key=lambda r: r.alias)
    return results


@router.get("/balances/trend")
def get_balance_trend(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
    days: int = Query(default=365, ge=7, le=730),
) -> list[dict]:
    """
    Daily net worth trend. Returns one data point per date with net worth
    and per-account balances. Uses the latest balance snapshot per account per day.
    """
    cutoff = date.today() - timedelta(days=days)
    accounts = db.query(Account).filter_by(is_active=True).all()
    account_map = {a.id: a for a in accounts}

    # Get all balances since cutoff
    balances = (
        db.query(Balance)
        .filter(Balance.balance_date >= cutoff)
        .order_by(Balance.balance_date, Balance.created_at.desc())
        .all()
    )

    # Group: date → account_id → latest balance (first seen due to created_at desc)
    from collections import defaultdict
    daily: dict[date, dict] = defaultdict(dict)
    for b in balances:
        acct = account_map.get(b.account_id)
        if not acct:
            continue
        day = b.balance_date
        if acct.alias not in daily[day]:
            daily[day][acct.alias] = {
                "amount": float(b.balance_amount),
                "type": acct.account_type,
            }

    # Build trend with net worth calculation
    result = []
    for day in sorted(daily.keys()):
        entry = daily[day]
        checking = entry.get("WF Checking", {}).get("amount", 0)
        brokerage = entry.get("Schwab Brokerage", {}).get("amount", 0)
        roth = entry.get("Schwab Roth IRA", {}).get("amount", 0)
        wf_cc = entry.get("WF Credit Card", {}).get("amount", 0)
        amex = entry.get("Amex Credit Card", {}).get("amount", 0)

        net_worth = checking + brokerage + roth - wf_cc - amex

        point: dict = {
            "date": day.isoformat(),
            "net_worth": round(net_worth, 2),
        }
        for alias, info in entry.items():
            point[alias] = info["amount"]

        result.append(point)

    return result
