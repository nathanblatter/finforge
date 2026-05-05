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
from models.db_models import Goal, GoalAlert
from schemas.schemas import AlertsListResponse, GoalAlertResponse

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=AlertsListResponse)
def list_alerts(
    include_acknowledged: bool = Query(default=False, description="Include already-acknowledged alerts"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> AlertsListResponse:
    """Active goal alerts. Unacknowledged only by default."""
    q = (
        db.query(GoalAlert, Goal.name.label("goal_name"))
        .join(Goal, GoalAlert.goal_id == Goal.id)
    )
    if not include_acknowledged:
        q = q.filter(GoalAlert.is_acknowledged.is_(False))
    rows = q.order_by(desc(GoalAlert.created_at)).all()

    alerts = [
        GoalAlertResponse(
            id=alert.id,
            goal_id=alert.goal_id,
            goal_name=goal_name,
            alert_type=alert.alert_type,
            message=alert.message,
            is_acknowledged=alert.is_acknowledged,
            acknowledged_at=alert.acknowledged_at,
            created_at=alert.created_at,
        )
        for alert, goal_name in rows
    ]

    return AlertsListResponse(
        alerts=alerts,
        total=len(alerts),
        unacknowledged_count=sum(1 for a in alerts if not a.is_acknowledged),
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=GoalAlertResponse)
def acknowledge_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> GoalAlertResponse:
    """Mark a goal alert as acknowledged."""
    alert = db.query(GoalAlert).filter_by(id=alert_id).first()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert.is_acknowledged = True
    alert.acknowledged_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(alert)

    goal = db.query(Goal).filter_by(id=alert.goal_id).first()
    return GoalAlertResponse(
        id=alert.id,
        goal_id=alert.goal_id,
        goal_name=goal.name if goal else "Unknown",
        alert_type=alert.alert_type,
        message=alert.message,
        is_acknowledged=alert.is_acknowledged,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )
