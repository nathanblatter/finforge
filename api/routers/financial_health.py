"""Financial health score — composite 0-100 score + drill-down breakdown,
monthly trend snapshots, and a month-over-month score-drop alert.

See api/services/financial_health.py for the formulas.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import FinancialHealthSnapshot, NatebotQueue, Notification
from services.financial_health import SCORE_DROP_ALERT_THRESHOLD, compute_health_score

logger = logging.getLogger("finforge.financial_health")

router = APIRouter(prefix="/financial-health", tags=["financial-health"])


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


@router.get("/current")
def get_current_health_score(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Live-computed composite score as of today (not read from a snapshot)."""
    return compute_health_score(db, date.today())


@router.get("/history")
def get_health_score_history(
    months: int = Query(default=24, ge=1, le=240),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Stored monthly snapshots, oldest first, for the trend line."""
    rows = (
        db.query(FinancialHealthSnapshot)
        .order_by(FinancialHealthSnapshot.snapshot_date.desc())
        .limit(months)
        .all()
    )
    rows = list(reversed(rows))
    return {
        "snapshots": [
            {
                "snapshot_date": r.snapshot_date.isoformat(),
                "composite_score": float(r.composite_score),
                "savings_rate_score": float(r.savings_rate_score),
                "savings_rate_value": float(r.savings_rate_value) if r.savings_rate_value is not None else None,
                "emergency_fund_score": float(r.emergency_fund_score),
                "emergency_fund_months": float(r.emergency_fund_months) if r.emergency_fund_months is not None else None,
                "expense_volatility_score": float(r.expense_volatility_score),
                "expense_volatility_cv": float(r.expense_volatility_cv) if r.expense_volatility_cv is not None else None,
                "allocation_drift_score": float(r.allocation_drift_score),
                "allocation_drift_value": float(r.allocation_drift_value) if r.allocation_drift_value is not None else None,
            }
            for r in rows
        ],
    }


def _upsert_snapshot(db: Session, snapshot_date: date, result: dict) -> FinancialHealthSnapshot:
    comps = result["components"]
    existing = db.query(FinancialHealthSnapshot).filter_by(snapshot_date=snapshot_date).first()
    if existing is None:
        existing = FinancialHealthSnapshot(id=uuid.uuid4(), snapshot_date=snapshot_date)
        db.add(existing)

    existing.composite_score = result["composite_score"]
    existing.savings_rate_score = comps["savings_rate"]["score"]
    existing.savings_rate_value = comps["savings_rate"]["value"]
    existing.emergency_fund_score = comps["emergency_fund"]["score"]
    existing.emergency_fund_months = comps["emergency_fund"]["value"]
    existing.expense_volatility_score = comps["expense_volatility"]["score"]
    existing.expense_volatility_cv = comps["expense_volatility"]["value"]
    existing.allocation_drift_score = comps["allocation_drift"]["score"]
    existing.allocation_drift_value = comps["allocation_drift"]["value"]
    db.flush()
    return existing


def _check_score_drop_alert(db: Session, snapshot_date: date, composite_score: float) -> None:
    """Notify (dual-write: Notification row + NateBot iMessage queue,
    mirroring cron/alerts_engine.py's dedup + queue_notification pattern)
    if the composite score dropped >SCORE_DROP_ALERT_THRESHOLD points vs the
    prior month's snapshot."""
    prev = (
        db.query(FinancialHealthSnapshot)
        .filter(FinancialHealthSnapshot.snapshot_date < snapshot_date)
        .order_by(FinancialHealthSnapshot.snapshot_date.desc())
        .first()
    )
    if prev is None:
        return
    drop = float(prev.composite_score) - float(composite_score)
    if drop <= SCORE_DROP_ALERT_THRESHOLD:
        return

    title = "Financial Health Score"
    alert_type = "score_drop"
    existing = (
        db.query(Notification)
        .filter(
            Notification.source == "financial_health",
            Notification.title == title,
            Notification.alert_type == alert_type,
            Notification.is_acknowledged.is_(False),
            Notification.created_at >= datetime(snapshot_date.year, snapshot_date.month, 1, tzinfo=timezone.utc),
        )
        .first()
    )
    if existing is not None:
        return

    message = (
        f"Your financial health score dropped {drop:.0f} points month-over-month "
        f"({float(prev.composite_score):.0f} → {float(composite_score):.0f})."
    )
    db.add(Notification(
        id=uuid.uuid4(),
        source="financial_health",
        title=title,
        alert_type=alert_type,
        message=message,
        is_acknowledged=False,
        created_at=datetime.now(timezone.utc),
    ))
    db.add(NatebotQueue(
        id=uuid.uuid4(),
        priority="normal",
        category="financial_health_alert",
        text=f"📉 {message}",
        delivered=False,
        created_at=datetime.now(timezone.utc),
    ))


@router.post("/snapshot")
def create_health_score_snapshot(
    for_date: Optional[str] = Query(default=None, description="YYYY-MM-DD — defaults to today"),
    backfill: bool = Query(default=False, description="Recompute + store a snapshot for every month with balance history, not just `for_date`"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Compute today's (or a given date's) score and store it as this
    month's snapshot. Called monthly by cron/main.py::financial_health_snapshot.
    Also runs the score-drop alert check. `backfill=true` walks every
    calendar month from the earliest balance record to now and (re)computes
    a snapshot for each — used once after the migration to seed history."""
    if backfill:
        from models.db_models import Balance
        earliest = db.query(Balance.balance_date).order_by(Balance.balance_date.asc()).first()
        if earliest is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No balance history to backfill from.")
        start = _first_of_month(earliest[0])
        today = date.today()
        created = []
        y, m = start.year, start.month
        while date(y, m, 1) <= today:
            snap_date = date(y, m, 1)
            # compute_health_score's trailing windows exclude the calendar month
            # containing `as_of` (to avoid partial-month skew on "current" calls).
            # To make month M's snapshot include M's own (complete, historical)
            # data, anchor on the first day of the month *after* M.
            as_of = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            as_of = min(as_of, today)
            result = compute_health_score(db, as_of)
            row = _upsert_snapshot(db, snap_date, result)
            created.append(row.snapshot_date.isoformat())
            m += 1
            if m == 13:
                m = 1
                y += 1
        db.commit()
        return {"backfilled": created}

    if for_date:
        try:
            target = date.fromisoformat(for_date)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid for_date, expected YYYY-MM-DD")
    else:
        target = date.today()

    snapshot_date = _first_of_month(target)
    result = compute_health_score(db, target)
    row = _upsert_snapshot(db, snapshot_date, result)
    _check_score_drop_alert(db, snapshot_date, float(row.composite_score))
    db.commit()

    return {
        "snapshot_date": snapshot_date.isoformat(),
        "composite_score": float(row.composite_score),
        "live_result": result,
    }
