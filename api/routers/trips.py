"""Trip tracker — define a trip (name, destination, date range, optional
budget) and every spending transaction inside the window is pulled in
automatically from checking/credit-card accounts (transfers and fixed
expenses excluded). Per-transaction overrides pull in pre-trip bookings
(flights, hotels paid months earlier) or kick out unrelated charges that
happened to post mid-trip. Cost analysis: totals, per-category and per-day
breakdowns, daily run-rate and budget burn."""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload

from auth import require_auth
from database import get_db
from models.db_models import Account, Transaction, Trip, TripTransactionOverride

router = APIRouter(prefix="/trips", tags=["trips"])

SPENDING_ACCOUNT_TYPES = ("checking", "credit_card")
# Money movement, not trip spend (debits-positive convention app-wide).
TRANSFER_CATEGORIES = {"Transfer", "Credit Card Payment", "Payment", "Investment Transfer"}
# How far back the candidate search reaches for pre-trip bookings.
CANDIDATE_LOOKBACK_DAYS = 180
CANDIDATE_LOOKAHEAD_DAYS = 30


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    destination: Optional[str] = Field(default=None, max_length=255)
    start_date: date
    end_date: date
    budget: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: date, info):
        start = info.data.get("start_date")
        if start is not None and v < start:
            raise ValueError("end_date must be on or after start_date")
        return v


class TripUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    destination: Optional[str] = Field(default=None, max_length=255)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = Field(default=None, ge=0)
    clear_budget: bool = False
    notes: Optional[str] = None


class OverrideBody(BaseModel):
    included: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_trip(db: Session, trip_id: uuid.UUID) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _trip_status(trip: Trip, today: date) -> str:
    if today < trip.start_date:
        return "upcoming"
    if today > trip.end_date:
        return "completed"
    return "active"


def _auto_transactions(db: Session, trip: Trip) -> list[tuple[Transaction, str]]:
    """Transactions auto-included by the trip's date window: spending
    accounts only, transfers and fixed expenses excluded."""
    rows = (
        db.query(Transaction, Account.alias)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= trip.start_date,
            Transaction.date <= trip.end_date,
            Account.account_type.in_(SPENDING_ACCOUNT_TYPES),
            Transaction.is_fixed_expense.is_(False),
        )
        .all()
    )
    return [(t, alias) for t, alias in rows if (t.category or "") not in TRANSFER_CATEGORIES]


def _resolved_transactions(db: Session, trip: Trip) -> list[dict]:
    """The trip's transaction set after overrides: auto window minus manual
    excludes, plus manual includes (any date). Each entry carries how it got
    here ('auto' | 'manual') so the UI can explain itself."""
    overrides = {o.transaction_id: o.included for o in trip.overrides}

    entries: dict[uuid.UUID, dict] = {}
    for t, alias in _auto_transactions(db, trip):
        if overrides.get(t.id) is False:
            continue
        entries[t.id] = _serialize_txn(t, alias, source="auto")

    manual_ids = [tid for tid, inc in overrides.items() if inc and tid not in entries]
    if manual_ids:
        rows = (
            db.query(Transaction, Account.alias)
            .join(Account, Transaction.account_id == Account.id)
            .filter(Transaction.id.in_(manual_ids))
            .all()
        )
        for t, alias in rows:
            entries[t.id] = _serialize_txn(t, alias, source="manual")

    return sorted(entries.values(), key=lambda e: (e["date"], e["merchant_name"] or ""))


def _serialize_txn(t: Transaction, alias: str, source: str) -> dict:
    return {
        "id": str(t.id),
        "date": t.date.isoformat(),
        "amount": float(t.amount),
        "merchant_name": t.merchant_name,
        "category": t.category,
        "subcategory": t.subcategory,
        "account_alias": alias,
        "is_pending": t.is_pending,
        "source": source,
    }


def _analyze(trip: Trip, txns: list[dict], today: date) -> dict:
    """Cost analysis over the resolved transaction set. Amounts are net
    (debits positive, refunds negative) so totals reflect true trip cost."""
    total = sum(t["amount"] for t in txns)
    pre_trip = sum(t["amount"] for t in txns if t["date"] < trip.start_date.isoformat())

    by_category: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0})
    by_day: dict[str, float] = defaultdict(float)
    for t in txns:
        cat = t["category"] or "Uncategorized"
        by_category[cat]["amount"] += t["amount"]
        by_category[cat]["count"] += 1
        by_day[t["date"]] += t["amount"]

    trip_days = (trip.end_date - trip.start_date).days + 1
    status = _trip_status(trip, today)
    if status == "upcoming":
        days_elapsed = 0
    elif status == "active":
        days_elapsed = (today - trip.start_date).days + 1
    else:
        days_elapsed = trip_days

    in_window = total - pre_trip
    daily_avg = in_window / days_elapsed if days_elapsed > 0 else None

    # Run-rate projection while the trip is live: what's already spent plus
    # the in-window daily average carried through the remaining days.
    projected_total = None
    if status == "active" and daily_avg is not None:
        projected_total = round(total + daily_avg * (trip_days - days_elapsed), 2)

    budget = float(trip.budget) if trip.budget is not None else None
    return {
        "total_spend": round(total, 2),
        "pre_trip_spend": round(pre_trip, 2),
        "in_window_spend": round(in_window, 2),
        "transaction_count": len(txns),
        "trip_days": trip_days,
        "days_elapsed": days_elapsed,
        "daily_avg": round(daily_avg, 2) if daily_avg is not None else None,
        "projected_total": projected_total,
        "budget": budget,
        "budget_remaining": round(budget - total, 2) if budget is not None else None,
        "budget_pct": round(total / budget * 100, 1) if budget else None,
        "by_category": sorted(
            (
                {"category": cat, "amount": round(v["amount"], 2), "count": v["count"]}
                for cat, v in by_category.items()
            ),
            key=lambda x: -x["amount"],
        ),
        "by_day": sorted(
            ({"date": d, "amount": round(a, 2)} for d, a in by_day.items()),
            key=lambda x: x["date"],
        ),
    }


def _serialize_trip(trip: Trip, today: date) -> dict:
    return {
        "id": str(trip.id),
        "name": trip.name,
        "destination": trip.destination,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "budget": float(trip.budget) if trip.budget is not None else None,
        "notes": trip.notes,
        "status": _trip_status(trip, today),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
def list_trips(db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    today = date.today()
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.overrides))
        .order_by(Trip.start_date.desc())
        .all()
    )
    items = []
    for trip in trips:
        txns = _resolved_transactions(db, trip)
        total = round(sum(t["amount"] for t in txns), 2)
        budget = float(trip.budget) if trip.budget is not None else None
        items.append({
            **_serialize_trip(trip, today),
            "total_spend": total,
            "transaction_count": len(txns),
            "budget_pct": round(total / budget * 100, 1) if budget else None,
        })
    return {"trips": items}


@router.post("", status_code=201)
def create_trip(body: TripCreate, db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    trip = Trip(
        name=body.name.strip(),
        destination=body.destination.strip() if body.destination else None,
        start_date=body.start_date,
        end_date=body.end_date,
        budget=body.budget,
        notes=body.notes,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return _serialize_trip(trip, date.today())


@router.get("/{trip_id}")
def get_trip(trip_id: uuid.UUID, db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    trip = _get_trip(db, trip_id)
    today = date.today()
    txns = _resolved_transactions(db, trip)
    return {
        **_serialize_trip(trip, today),
        "summary": _analyze(trip, txns, today),
        "transactions": txns,
    }


@router.put("/{trip_id}")
def update_trip(
    trip_id: uuid.UUID,
    body: TripUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    trip = _get_trip(db, trip_id)
    if body.name is not None:
        trip.name = body.name.strip()
    if body.destination is not None:
        trip.destination = body.destination.strip() or None
    if body.start_date is not None:
        trip.start_date = body.start_date
    if body.end_date is not None:
        trip.end_date = body.end_date
    if trip.end_date < trip.start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if body.clear_budget:
        trip.budget = None
    elif body.budget is not None:
        trip.budget = body.budget
    if body.notes is not None:
        trip.notes = body.notes
    db.commit()
    db.refresh(trip)
    return _serialize_trip(trip, date.today())


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: uuid.UUID, db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    trip = _get_trip(db, trip_id)
    db.delete(trip)
    db.commit()


# ---------------------------------------------------------------------------
# Per-transaction overrides
# ---------------------------------------------------------------------------

@router.put("/{trip_id}/transactions/{transaction_id}")
def set_override(
    trip_id: uuid.UUID,
    transaction_id: uuid.UUID,
    body: OverrideBody,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    trip = _get_trip(db, trip_id)
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    override = (
        db.query(TripTransactionOverride)
        .filter(
            TripTransactionOverride.trip_id == trip.id,
            TripTransactionOverride.transaction_id == txn.id,
        )
        .first()
    )
    if override is None:
        override = TripTransactionOverride(trip_id=trip.id, transaction_id=txn.id, included=body.included)
        db.add(override)
    else:
        override.included = body.included
    db.commit()
    return {"trip_id": str(trip.id), "transaction_id": str(txn.id), "included": body.included}


@router.delete("/{trip_id}/transactions/{transaction_id}", status_code=204)
def clear_override(
    trip_id: uuid.UUID,
    transaction_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    trip = _get_trip(db, trip_id)
    (
        db.query(TripTransactionOverride)
        .filter(
            TripTransactionOverride.trip_id == trip.id,
            TripTransactionOverride.transaction_id == transaction_id,
        )
        .delete()
    )
    db.commit()


# ---------------------------------------------------------------------------
# Candidate search — pull in pre-trip bookings (flights, hotels, deposits)
# ---------------------------------------------------------------------------

@router.get("/{trip_id}/candidates")
def list_candidates(
    trip_id: uuid.UUID,
    q: Optional[str] = Query(default=None, max_length=100, description="Merchant/category search"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    trip = _get_trip(db, trip_id)
    included_ids = {uuid.UUID(t["id"]) for t in _resolved_transactions(db, trip)}

    query = (
        db.query(Transaction, Account.alias)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= trip.start_date - timedelta(days=CANDIDATE_LOOKBACK_DAYS),
            Transaction.date <= trip.end_date + timedelta(days=CANDIDATE_LOOKAHEAD_DAYS),
            Account.account_type.in_(SPENDING_ACCOUNT_TYPES),
        )
    )
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            Transaction.merchant_name.ilike(pattern) | Transaction.category.ilike(pattern)
        )
    rows = query.order_by(Transaction.date.desc()).limit(limit * 3).all()

    items = [
        _serialize_txn(t, alias, source="candidate")
        for t, alias in rows
        if t.id not in included_ids
    ][:limit]
    return {"candidates": items}
