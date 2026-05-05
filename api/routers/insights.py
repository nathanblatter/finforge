"""GET /api/v1/insights/latest — latest Claude-generated insights by type."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import ClaudeInsight
from schemas.schemas import InsightResponse, InsightsResponse

router = APIRouter(tags=["insights"])

_VALID_TYPES = frozenset({
    "spending_pattern",
    "goal_trajectory",
    "savings_opportunity",
    "anomaly",
})


@router.get("/insights/latest", response_model=InsightsResponse)
def get_latest_insights(
    types: Optional[str] = Query(
        default=None,
        description="Comma-separated insight types to filter. Valid: spending_pattern, goal_trajectory, savings_opportunity, anomaly",
    ),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> InsightsResponse:
    """
    Latest non-expired insight for each type (one per type).
    Used by NateBot for insight delivery and the dashboard insight panel.
    """
    now = datetime.now(tz=timezone.utc)

    if types is not None:
        requested = {t.strip() for t in types.split(",") if t.strip()}
        type_filter = requested & _VALID_TYPES
    else:
        type_filter = _VALID_TYPES

    if not type_filter:
        return InsightsResponse(insights=[], generated_at=now)

    # Subquery: most recent insight_date per type among non-expired rows
    subq = (
        db.query(
            ClaudeInsight.insight_type,
            func.max(ClaudeInsight.insight_date).label("max_date"),
        )
        .filter(
            ClaudeInsight.expires_at > now,
            ClaudeInsight.insight_type.in_(type_filter),
        )
        .group_by(ClaudeInsight.insight_type)
        .subquery()
    )

    # Join back to retrieve the full row for each (type, max_date)
    rows = (
        db.query(ClaudeInsight)
        .join(
            subq,
            (ClaudeInsight.insight_type == subq.c.insight_type)
            & (ClaudeInsight.insight_date == subq.c.max_date),
        )
        .filter(ClaudeInsight.expires_at > now)
        .order_by(ClaudeInsight.insight_date.desc())
        .all()
    )

    return InsightsResponse(
        insights=[InsightResponse.model_validate(r) for r in rows],
        generated_at=now,
    )
