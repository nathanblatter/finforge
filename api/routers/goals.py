"""
GET    /api/v1/goals              — all goals with progress badges
GET    /api/v1/goals/{id}         — single goal with full snapshot history
POST   /api/v1/goals              — create a new goal
PUT    /api/v1/goals/{id}         — update mutable goal fields
PATCH  /api/v1/goals/{id}/status  — change goal status
DELETE /api/v1/goals/{id}         — hard delete
"""

import json
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, extract
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance, Goal, GoalSnapshot, Holding, Transaction
from schemas.schemas import (
    GoalCreateRequest,
    GoalUpdateRequest,
    GoalStatusPatch,
    GoalDetailResponse,
    GoalProgressResponse,
    GoalSnapshotItem,
    GoalsListResponse,
)

router = APIRouter(tags=["goals"])


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def _progress_status(goal: Goal, latest: Optional[GoalSnapshot]) -> str:
    """
    Compute PRD progress badge: On Track / At Risk / Off Track / Completed / No Data.
    Thresholds: >= 90% = On Track, >= 70% = At Risk, else Off Track.
    """
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


def _projected_completion(snapshots: list[GoalSnapshot]) -> Optional[date]:
    """
    Linear extrapolation from two most recent snapshots.
    Returns None if < 2 snapshots or trajectory is flat/negative.
    """
    if len(snapshots) < 2:
        return None
    newer, older = snapshots[0], snapshots[1]
    delta_days = (newer.snapshot_date - older.snapshot_date).days
    if delta_days <= 0:
        return None
    delta_pct = float(newer.pct_complete) - float(older.pct_complete)
    if delta_pct <= 0:
        return None
    days_to_go = (100.0 - float(newer.pct_complete)) / delta_pct * delta_days
    return newer.snapshot_date + timedelta(days=int(days_to_go))


def _build_progress(goal: Goal, snapshots: list[GoalSnapshot]) -> GoalProgressResponse:
    latest = snapshots[0] if snapshots else None
    return GoalProgressResponse(
        id=goal.id,
        name=goal.name,
        goal_type=goal.goal_type,
        target_value=goal.target_value,
        target_date=goal.target_date,
        direction=goal.direction,
        cadence=goal.cadence,
        alert_threshold=goal.alert_threshold,
        natebot_enabled=goal.natebot_enabled,
        status=goal.status,
        current_value=latest.current_value if latest else None,
        pct_complete=latest.pct_complete if latest else None,
        progress_status=_progress_status(goal, latest),
        projected_completion_date=_projected_completion(snapshots),
        last_snapshot_date=latest.snapshot_date if latest else None,
    )


def _build_detail(goal: Goal, snapshots: list[GoalSnapshot]) -> GoalDetailResponse:
    """Build GoalDetailResponse including full snapshot history."""
    latest = snapshots[0] if snapshots else None
    return GoalDetailResponse(
        id=goal.id,
        name=goal.name,
        goal_type=goal.goal_type,
        metric_source=goal.metric_source,
        target_value=goal.target_value,
        target_date=goal.target_date,
        direction=goal.direction,
        cadence=goal.cadence,
        alert_threshold=goal.alert_threshold,
        natebot_enabled=goal.natebot_enabled,
        status=goal.status,
        progress_status=_progress_status(goal, latest),
        current_value=latest.current_value if latest else None,
        pct_complete=latest.pct_complete if latest else None,
        projected_completion_date=_projected_completion(snapshots),
        snapshots=[
            GoalSnapshotItem(
                snapshot_date=s.snapshot_date,
                current_value=s.current_value,
                target_value=s.target_value,
                pct_complete=s.pct_complete,
            )
            for s in snapshots
        ],
    )


def _get_snapshots(db: Session, goal_id: uuid.UUID) -> list[GoalSnapshot]:
    return (
        db.query(GoalSnapshot)
        .filter_by(goal_id=goal_id)
        .order_by(desc(GoalSnapshot.snapshot_date))
        .all()
    )


# ---------------------------------------------------------------------------
# Metric resolution (mirrors cron/goal_engine.py logic for initial snapshot)
# ---------------------------------------------------------------------------

def _resolve_metric(db: Session, goal: Goal) -> Optional[Decimal]:
    """Compute current metric value for a goal from live DB data."""
    if not goal.metric_source:
        return None
    try:
        source = json.loads(goal.metric_source)
    except (json.JSONDecodeError, TypeError):
        return None

    if goal.goal_type == "balance_target":
        aliases = source.get("aliases", [])
        if not aliases:
            return None
        total = Decimal("0")
        for alias in aliases:
            acct = db.query(Account).filter(Account.alias == alias, Account.is_active.is_(True)).first()
            if not acct:
                continue
            bal = db.query(Balance).filter_by(account_id=acct.id).order_by(desc(Balance.balance_date)).first()
            if not bal:
                continue
            amt = bal.balance_amount
            if acct.account_type == "credit_card":
                amt = abs(amt)
            total += amt
        return total

    elif goal.goal_type == "spend_limit":
        categories = source.get("categories", [])
        if not categories:
            return None
        today = date.today()
        month_str = source.get("month")
        if month_str:
            try:
                year, month = int(month_str[:4]), int(month_str[5:7])
            except (ValueError, IndexError):
                year, month = today.year, today.month
        else:
            year, month = today.year, today.month
        rows = (
            db.query(Transaction)
            .filter(
                Transaction.category.in_(categories),
                Transaction.is_fixed_expense.is_(False),
                Transaction.is_pending.is_(False),
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
            )
            .all()
        )
        total = sum((r.amount for r in rows if r.amount > 0), Decimal("0"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    elif goal.goal_type == "contribution_rate":
        alias = source.get("alias", "")
        if not alias:
            return None
        acct = db.query(Account).filter(Account.alias == alias, Account.is_active.is_(True)).first()
        if not acct:
            return None
        bal = (
            db.query(Balance)
            .filter(Balance.account_id == acct.id, Balance.balance_type == "portfolio_value")
            .order_by(desc(Balance.balance_date))
            .first()
        )
        return bal.balance_amount if bal else None

    elif goal.goal_type == "portfolio_growth":
        alias = source.get("alias", "")
        if not alias:
            return None
        acct = db.query(Account).filter(Account.alias == alias, Account.is_active.is_(True)).first()
        if not acct:
            return None
        bal = db.query(Balance).filter_by(account_id=acct.id).order_by(desc(Balance.balance_date)).first()
        return bal.balance_amount if bal else None

    return None


def _compute_pct(goal: Goal, current_value: Decimal) -> Decimal:
    target = Decimal(str(goal.target_value))
    if target == 0:
        return Decimal("100.00")
    if goal.direction == "increase":
        raw = current_value / target * 100
        pct = min(raw, Decimal("100"))
    elif goal.direction == "decrease":
        raw = (1 - current_value / target) * 100
        pct = max(raw, Decimal("0"))
    elif goal.direction == "maintain":
        deviation = abs(current_value - target) / target * 100
        pct = Decimal("100") if deviation <= 10 else Decimal("50")
    else:
        pct = Decimal("0")
    return pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _create_initial_snapshot(db: Session, goal: Goal) -> None:
    """Compute and insert an initial snapshot so the goal shows progress immediately."""
    current = _resolve_metric(db, goal)
    if current is None:
        return
    pct = _compute_pct(goal, current)
    db.add(GoalSnapshot(
        id=uuid.uuid4(),
        goal_id=goal.id,
        snapshot_date=date.today(),
        current_value=current,
        target_value=goal.target_value,
        pct_complete=pct,
    ))


# ---------------------------------------------------------------------------
# GET /goals/templates — available auto-track presets
# ---------------------------------------------------------------------------

@router.get("/goals/templates")
def get_goal_templates(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Return available auto-trackable goal presets based on current accounts."""
    accounts = db.query(Account).filter_by(is_active=True).all()
    alias_map = {a.alias: a.account_type for a in accounts}

    templates = []

    # Portfolio growth for each brokerage/ira account
    for alias, atype in alias_map.items():
        if atype in ("brokerage", "ira"):
            label = f"Grow {alias}" if atype == "brokerage" else f"Grow {alias}"
            templates.append({
                "id": f"portfolio_growth_{alias.lower().replace(' ', '_')}",
                "name": label,
                "goal_type": "portfolio_growth",
                "direction": "increase",
                "metric_source": json.dumps({"alias": alias}),
                "description": f"Track {alias} total balance toward a target",
            })

    # Net worth (balance_target across all accounts)
    if accounts:
        all_aliases = [a.alias for a in accounts]
        templates.append({
            "id": "net_worth_target",
            "name": "Net Worth Target",
            "goal_type": "balance_target",
            "direction": "increase",
            "metric_source": json.dumps({"aliases": all_aliases}),
            "description": "Track combined balance of all accounts",
        })

    # Savings target (brokerage only)
    brokerage_aliases = [a.alias for a in accounts if a.account_type == "brokerage"]
    if brokerage_aliases:
        templates.append({
            "id": "savings_target",
            "name": "Savings Target",
            "goal_type": "balance_target",
            "direction": "increase",
            "metric_source": json.dumps({"aliases": brokerage_aliases}),
            "description": "Track brokerage savings toward a target",
        })

    # IRA contribution (contribution_rate)
    ira_aliases = [a.alias for a in accounts if a.account_type == "ira"]
    for alias in ira_aliases:
        templates.append({
            "id": f"ira_contribution_{alias.lower().replace(' ', '_')}",
            "name": f"{alias} Contribution Target",
            "goal_type": "contribution_rate",
            "direction": "increase",
            "metric_source": json.dumps({"alias": alias}),
            "description": f"Track {alias} portfolio value toward a contribution target",
        })

    # Spending limit (all non-fixed categories)
    categories = (
        db.query(Transaction.category)
        .filter(
            Transaction.category.isnot(None),
            Transaction.is_fixed_expense.is_(False),
        )
        .distinct()
        .all()
    )
    cat_list = sorted([c[0] for c in categories if c[0]])
    if cat_list:
        templates.append({
            "id": "monthly_spend_limit",
            "name": "Monthly Spending Limit",
            "goal_type": "spend_limit",
            "direction": "decrease",
            "metric_source": json.dumps({"categories": cat_list}),
            "description": f"Keep monthly discretionary spending under a target",
        })

    # Credit card payoff (balance_target, decrease)
    cc_aliases = [a.alias for a in accounts if a.account_type == "credit_card"]
    if cc_aliases:
        templates.append({
            "id": "cc_payoff",
            "name": "Credit Card Payoff",
            "goal_type": "balance_target",
            "direction": "decrease",
            "metric_source": json.dumps({"aliases": cc_aliases}),
            "description": "Pay off credit card balances",
        })

    return {"templates": templates}


# ---------------------------------------------------------------------------
# GET /goals
# ---------------------------------------------------------------------------

@router.get("/goals", response_model=GoalsListResponse)
def list_goals(
    status: Optional[str] = Query(default="active", description="Filter by status (active/paused/completed/failed). Omit for all."),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalsListResponse:
    """All goals with latest snapshot and progress badge."""
    q = db.query(Goal)
    if status:
        q = q.filter(Goal.status == status)
    goals = q.all()

    responses = []
    for goal in goals:
        snapshots = _get_snapshots(db, goal.id)
        responses.append(_build_progress(goal, snapshots))

    return GoalsListResponse(goals=responses, total=len(responses))


# ---------------------------------------------------------------------------
# GET /goals/{goal_id}
# ---------------------------------------------------------------------------

@router.get("/goals/{goal_id}", response_model=GoalDetailResponse)
def get_goal(
    goal_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalDetailResponse:
    """Single goal with full snapshot history (newest first)."""
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return _build_detail(goal, _get_snapshots(db, goal.id))


# ---------------------------------------------------------------------------
# POST /goals
# ---------------------------------------------------------------------------

@router.post("/goals", response_model=GoalDetailResponse, status_code=201)
def create_goal(
    payload: GoalCreateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalDetailResponse:
    """Create a new goal. No snapshots exist yet; progress_status will be 'No Data'."""
    now = datetime.now(tz=timezone.utc)
    goal = Goal(
        id=uuid.uuid4(),
        name=payload.name,
        goal_type=payload.goal_type,
        metric_source=payload.metric_source,
        target_value=payload.target_value,
        target_date=payload.target_date,
        direction=payload.direction,
        cadence=payload.cadence,
        alert_threshold=payload.alert_threshold,
        natebot_enabled=payload.natebot_enabled,
        status="active",
    )
    db.add(goal)
    db.flush()

    # Compute initial snapshot so progress shows immediately
    _create_initial_snapshot(db, goal)

    db.commit()
    db.refresh(goal)
    return _build_detail(goal, _get_snapshots(db, goal.id))


# ---------------------------------------------------------------------------
# PUT /goals/{goal_id}
# ---------------------------------------------------------------------------

@router.put("/goals/{goal_id}", response_model=GoalDetailResponse)
def update_goal(
    goal_id: uuid.UUID,
    payload: GoalUpdateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalDetailResponse:
    """Update mutable goal fields. Only supplied fields are written."""
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)

    db.commit()
    db.refresh(goal)
    return _build_detail(goal, _get_snapshots(db, goal.id))


# ---------------------------------------------------------------------------
# PATCH /goals/{goal_id}/status
# ---------------------------------------------------------------------------

@router.patch("/goals/{goal_id}/status", response_model=GoalDetailResponse)
def patch_goal_status(
    goal_id: uuid.UUID,
    payload: GoalStatusPatch,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalDetailResponse:
    """Change a goal's status (active / paused / completed / failed)."""
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.status = payload.status
    db.commit()
    db.refresh(goal)
    return _build_detail(goal, _get_snapshots(db, goal.id))


# ---------------------------------------------------------------------------
# DELETE /goals/{goal_id}
# ---------------------------------------------------------------------------

@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(
    goal_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> Response:
    """Hard-delete a goal and all its snapshots (CASCADE)."""
    goal = db.query(Goal).filter_by(id=goal_id).first()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    db.delete(goal)
    db.commit()
    return Response(status_code=204)
