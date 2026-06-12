"""
GET  /api/v1/alerts              — active goal alerts
POST /api/v1/alerts/{id}/acknowledge — mark alert as acknowledged
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Goal, GoalAlert, Notification
from schemas.schemas import AlertsListResponse, GoalAlertResponse

router = APIRouter(tags=["alerts"])


def _goal_alert_to_item(alert: GoalAlert, goal_name: str) -> GoalAlertResponse:
    return GoalAlertResponse(
        id=alert.id,
        source="goal",
        title=goal_name,
        goal_id=alert.goal_id,
        goal_name=goal_name,
        alert_type=alert.alert_type,
        message=alert.message,
        is_acknowledged=alert.is_acknowledged,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )


def _notification_to_item(n: Notification) -> GoalAlertResponse:
    return GoalAlertResponse(
        id=n.id,
        source=n.source,
        title=n.title,
        goal_id=None,
        goal_name=None,
        alert_type=n.alert_type,
        message=n.message,
        is_acknowledged=n.is_acknowledged,
        acknowledged_at=n.acknowledged_at,
        created_at=n.created_at,
    )


@router.get("/alerts", response_model=AlertsListResponse)
def list_alerts(
    include_acknowledged: bool = Query(default=False, description="Include already-acknowledged alerts"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> AlertsListResponse:
    """Unified alert feed — goal alerts plus generic notifications (budget, price).
    Unacknowledged only by default."""
    gq = db.query(GoalAlert, Goal.name.label("goal_name")).join(Goal, GoalAlert.goal_id == Goal.id)
    nq = db.query(Notification)
    if not include_acknowledged:
        gq = gq.filter(GoalAlert.is_acknowledged.is_(False))
        nq = nq.filter(Notification.is_acknowledged.is_(False))

    items = [_goal_alert_to_item(a, name) for a, name in gq.all()]
    items += [_notification_to_item(n) for n in nq.order_by(desc(Notification.created_at)).all()]
    items.sort(key=lambda a: a.created_at, reverse=True)

    return AlertsListResponse(
        alerts=items,
        total=len(items),
        unacknowledged_count=sum(1 for a in items if not a.is_acknowledged),
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=GoalAlertResponse)
def acknowledge_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalAlertResponse:
    """Mark an alert as acknowledged. Works for goal alerts and notifications."""
    now = datetime.now(tz=timezone.utc)

    alert = db.query(GoalAlert).filter_by(id=alert_id).first()
    if alert is not None:
        alert.is_acknowledged = True
        alert.acknowledged_at = now
        db.commit()
        db.refresh(alert)
        goal = db.query(Goal).filter_by(id=alert.goal_id).first()
        return _goal_alert_to_item(alert, goal.name if goal else "Unknown")

    note = db.query(Notification).filter_by(id=alert_id).first()
    if note is not None:
        note.is_acknowledged = True
        note.acknowledged_at = now
        db.commit()
        db.refresh(note)
        return _notification_to_item(note)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
