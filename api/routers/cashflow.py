"""
GET /api/v1/cashflow/runway   — projected checking balance 14-180 days out,
                                 with an uncertainty band and floor crossing.
GET /api/v1/cashflow/settings — read the configured balance floor + alert lead time.
PUT /api/v1/cashflow/settings — update the balance floor + alert lead time.

Distinct from /spending/bills-forecast (which projects a bill calendar out to
30 days): this endpoint answers "will I have enough on date X", combining the
same recurring bill/income detection with a confidence band sized from
historical discretionary-spend variance, and a configurable floor.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median, pstdev

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, CashflowSettings, Transaction
from services.recurring import (
    BILL_EXCLUDED_CATEGORIES,
    current_checking_balance,
    project_recurring_events,
)

router = APIRouter(tags=["cashflow"])

DEFAULT_DAYS = 90
DISCRETIONARY_LOOKBACK_DAYS = 90
# Width of the confidence band, in standard deviations of daily discretionary
# spend, compounded as sqrt(days) (simple random-walk assumption). z=1 is
# roughly a 68% band — this is a heuristic, not a formal statistical
# guarantee, consistent with the "approximate" framing of bills-forecast.
BAND_Z = 1.0


class CashflowSettingsBody(BaseModel):
    floor_amount: Decimal = Field(..., ge=0)
    lead_time_days: int = Field(default=14, ge=1, le=90)


def _get_or_create_settings(db: Session) -> CashflowSettings:
    """Single-row settings table (this is a single-user app) — create with
    defaults on first access."""
    settings = db.query(CashflowSettings).order_by(CashflowSettings.created_at.asc()).first()
    if settings is None:
        settings = CashflowSettings(floor_amount=Decimal("0"), lead_time_days=14)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _settings_dict(s: CashflowSettings) -> dict:
    return {
        "floor_amount": float(s.floor_amount),
        "lead_time_days": s.lead_time_days,
        "updated_at": s.updated_at.isoformat(),
    }


@router.get("/cashflow/settings")
def get_cashflow_settings(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    return _settings_dict(_get_or_create_settings(db))


@router.put("/cashflow/settings")
def update_cashflow_settings(
    body: CashflowSettingsBody,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    settings = _get_or_create_settings(db)
    settings.floor_amount = body.floor_amount
    settings.lead_time_days = body.lead_time_days
    db.commit()
    db.refresh(settings)
    return _settings_dict(settings)


def _discretionary_daily_series(db: Session, today: date, recurring_merchants: set[str]) -> list[float]:
    """Daily total of non-recurring checking-account debit spend over the
    trailing DISCRETIONARY_LOOKBACK_DAYS — the 'everything else' outflow not
    already accounted for by a detected recurring bill. Zero-filled for days
    with no spend. Used to size the projection's uncertainty band and to
    estimate a baseline daily discretionary drift."""
    since = today - timedelta(days=DISCRETIONARY_LOOKBACK_DAYS)
    rows = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= since,
            Transaction.date < today,
            Transaction.is_pending.is_(False),
            Transaction.amount > 0,  # debits only
            Account.account_type == "checking",
        )
        .all()
    )
    n_days = max((today - since).days, 1)
    by_day: dict[date, float] = {since + timedelta(days=d): 0.0 for d in range(n_days)}
    for t, a in rows:
        cat = (t.category or "").strip().lower()
        if cat in BILL_EXCLUDED_CATEGORIES:
            continue
        if t.merchant_name and t.merchant_name.strip() in recurring_merchants:
            continue
        by_day[t.date] = by_day.get(t.date, 0.0) + float(t.amount)
    return list(by_day.values())


@router.get("/cashflow/runway")
def get_runway(
    days: int = Query(default=DEFAULT_DAYS, ge=14, le=180),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Project the checking balance forward `days` days: recurring bills,
    detected income/paychecks, and a discretionary-spend confidence band on
    top. Reports whether/when the projection crosses the configured floor,
    both on the central estimate and on the conservative (low) band edge —
    the low-band crossing is the earlier, more cautious warning used for
    alerting."""
    today = date.today()
    horizon = today + timedelta(days=days)

    events = project_recurring_events(db, today, horizon)
    checking_balance = current_checking_balance(db)
    settings = _get_or_create_settings(db)
    floor = float(settings.floor_amount)

    recurring_merchants = {e["merchant"] for e in events}
    daily_discretionary = _discretionary_daily_series(db, today, recurring_merchants)
    daily_median = median(daily_discretionary) if daily_discretionary else 0.0
    daily_stdev = pstdev(daily_discretionary) if len(daily_discretionary) > 1 else 0.0

    events_by_date: dict[date, list[dict]] = defaultdict(list)
    for e in events:
        events_by_date[e["date"]].append(e)

    series: list[dict] = []
    central_crossing: date | None = None
    band_crossing: date | None = None

    if checking_balance is not None:
        running_central = checking_balance
        running_optimistic = checking_balance  # recurring-only path, ignores discretionary spend entirely
        for i in range(1, days + 1):
            d = today + timedelta(days=i)
            for e in events_by_date.get(d, []):
                running_central += e["amount"]
                running_optimistic += e["amount"]
            # Baseline drift: typical day's discretionary spend, layered on
            # top of the recurring-only path.
            running_central -= daily_median
            uncertainty = BAND_Z * daily_stdev * (i ** 0.5)
            low = running_central - uncertainty
            high = min(running_optimistic, running_central + uncertainty)
            series.append({
                "date": d.isoformat(),
                "balance": round(running_central, 2),
                "low": round(low, 2),
                "high": round(high, 2),
            })
            if central_crossing is None and running_central < floor:
                central_crossing = d
            if band_crossing is None and low < floor:
                band_crossing = d

    # Recurring-events-only running balance (mirrors bills-forecast's
    # balance_after) — a simpler complement to the smoothed daily `series`,
    # useful for the driver-events table.
    result_events = []
    if checking_balance is not None:
        running = checking_balance
        for e in events:
            running += e["amount"]
            item = dict(e)
            item["date"] = e["date"].isoformat()
            item["balance_after"] = round(running, 2)
            result_events.append(item)
    else:
        for e in events:
            item = dict(e)
            item["date"] = e["date"].isoformat()
            item["balance_after"] = None
            result_events.append(item)

    crossing = None
    if central_crossing is not None:
        crossing = {"date": central_crossing.isoformat(), "lead_time_days": (central_crossing - today).days}

    earliest_risk_crossing = None
    if band_crossing is not None:
        earliest_risk_crossing = {
            "date": band_crossing.isoformat(),
            "lead_time_days": (band_crossing - today).days,
        }

    return {
        "as_of": today.isoformat(),
        "days": days,
        "checking_balance": checking_balance,
        "floor_amount": floor,
        "lead_time_days_setting": settings.lead_time_days,
        "daily_discretionary_median": round(daily_median, 2),
        "daily_discretionary_stdev": round(daily_stdev, 2),
        "series": series,
        "events": result_events,
        # Central-estimate crossing — the "best guess" answer to "will I have enough on date X".
        "crossing": crossing,
        # Conservative low-band crossing — used for early/floor alerting.
        "earliest_risk_crossing": earliest_risk_crossing,
    }
