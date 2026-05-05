"""
GET /api/v1/natebot/briefing        — combined morning briefing payload
GET /api/v1/natebot/weekly-spending — week-over-week discretionary CC spend
"""

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import (
    Account,
    Balance,
    ClaudeInsight,
    Goal,
    GoalAlert,
    GoalSnapshot,
    NatebotEvent,
    Transaction,
)
from schemas.schemas import (
    CategorySpend,
    NatebotBriefingResponse,
    NatebotGoalSummary,
    WeeklySpendingComparison,
)

router = APIRouter(tags=["natebot"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_balance(db: Session, alias: str) -> Decimal:
    account = db.query(Account).filter_by(alias=alias).first()
    if account is None:
        return Decimal("0")
    balance = (
        db.query(Balance)
        .filter_by(account_id=account.id)
        .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
        .first()
    )
    return balance.balance_amount if balance else Decimal("0")


def _progress_status(goal: Goal, latest: Optional[GoalSnapshot]) -> str:
    if goal.status == "completed":
        return "Completed"
    if latest is None:
        return "No Data"
    pct = float(latest.pct_complete)
    if pct >= 100:
        return "Completed"
    if pct >= 90:
        return "On Track"
    if pct >= 70:
        return "At Risk"
    return "Off Track"


def _log_event(db: Session, event_type: str, response_dict: dict) -> None:
    db.add(NatebotEvent(
        id=uuid.uuid4(),
        timestamp=datetime.now(tz=timezone.utc),
        event_type=event_type,
        payload_hash=hashlib.sha256(
            json.dumps(response_dict, default=str).encode()
        ).hexdigest(),
    ))
    db.commit()


# ---------------------------------------------------------------------------
# GET /natebot/briefing
# ---------------------------------------------------------------------------

@router.get("/natebot/briefing", response_model=NatebotBriefingResponse)
def get_briefing(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> NatebotBriefingResponse:
    """Combined morning briefing: balances + natebot-enabled goals + alerts + insight."""
    wf_checking = _latest_balance(db, "WF Checking")
    schwab_brokerage = _latest_balance(db, "Schwab Brokerage")
    schwab_roth = _latest_balance(db, "Schwab Roth IRA")
    wf_cc = _latest_balance(db, "WF Credit Card")
    amex = _latest_balance(db, "Amex Credit Card")

    net_worth = wf_checking + schwab_brokerage + schwab_roth - wf_cc - amex
    savings_balance = schwab_brokerage
    liquid_cash = wf_checking
    cc_balance_owed = wf_cc + amex

    # Goals with natebot_enabled
    goals = (
        db.query(Goal)
        .filter(Goal.status == "active", Goal.natebot_enabled == True)
        .all()
    )
    goal_summaries = []
    for goal in goals:
        snap = (
            db.query(GoalSnapshot)
            .filter_by(goal_id=goal.id)
            .order_by(desc(GoalSnapshot.snapshot_date))
            .first()
        )
        goal_summaries.append(NatebotGoalSummary(
            name=goal.name,
            pct_complete=snap.pct_complete if snap else None,
            progress_status=_progress_status(goal, snap),
            target_value=goal.target_value,
            current_value=snap.current_value if snap else None,
        ))

    unacknowledged_alerts = (
        db.query(GoalAlert)
        .filter(GoalAlert.is_acknowledged == False)
        .count()
    )

    now = datetime.now(tz=timezone.utc)
    insight_row = (
        db.query(ClaudeInsight)
        .filter(ClaudeInsight.expires_at > now)
        .order_by(desc(ClaudeInsight.created_at))
        .first()
    )

    response = NatebotBriefingResponse(
        net_worth=net_worth,
        savings_balance=savings_balance,
        liquid_cash=liquid_cash,
        cc_balance_owed=cc_balance_owed,
        goals=goal_summaries,
        unacknowledged_alerts=unacknowledged_alerts,
        latest_insight=insight_row.content if insight_row else None,
        as_of=date.today(),
    )

    _log_event(db, "morning_briefing", response.model_dump())
    return response


# ---------------------------------------------------------------------------
# GET /natebot/weekly-spending
# ---------------------------------------------------------------------------

@router.get("/natebot/weekly-spending", response_model=WeeklySpendingComparison)
def get_weekly_spending(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> WeeklySpendingComparison:
    """Week-over-week discretionary CC spend comparison."""
    today = date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)

    cc_ids = [
        a.id for a in
        db.query(Account).filter(Account.account_type == "credit_card").all()
    ]

    def _week_txns(start: date, end: date) -> list[Transaction]:
        return (
            db.query(Transaction)
            .filter(
                Transaction.account_id.in_(cc_ids),
                Transaction.is_fixed_expense == False,
                Transaction.is_pending == False,
                Transaction.date >= start,
                Transaction.date <= end,
            )
            .all()
        )

    this_txns = _week_txns(this_monday, today)
    last_txns = _week_txns(last_monday, last_sunday)

    this_total = sum((t.amount for t in this_txns), Decimal("0"))
    last_total = sum((t.amount for t in last_txns), Decimal("0"))
    change = this_total - last_total
    change_pct = (change / last_total * 100).quantize(Decimal("0.01")) if last_total else None

    cat_totals: dict[str, Decimal] = {}
    for t in this_txns:
        cat = t.category or "Other"
        cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + t.amount

    top_cats = [
        CategorySpend(
            category=cat,
            amount=amt,
            pct_of_total=(amt / this_total * 100).quantize(Decimal("0.01")) if this_total else Decimal("0"),
        )
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    response = WeeklySpendingComparison(
        this_week_total=this_total,
        last_week_total=last_total,
        change_amount=change,
        change_pct=change_pct,
        this_week_top_categories=top_cats,
        period_start=this_monday,
        period_end=today,
    )

    _log_event(db, "weekly_spending", response.model_dump())
    return response
