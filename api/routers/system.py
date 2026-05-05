"""System and admin endpoints for FinForge operational monitoring."""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from fastapi.responses import JSONResponse

from auth import require_auth
from database import get_db
from dependencies import verify_api_key
from models.db_models import ClaudeInsight, CronLog, GoalSnapshot, Holding, NatebotEvent, Transaction

logger = logging.getLogger("finforge.api.system")

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/sync-status")
def get_sync_status(db: Session = Depends(get_db)):
    """Last successful sync timestamps for each data source."""
    plaid_last = db.query(func.max(Transaction.created_at)).scalar()
    schwab_last = db.query(func.max(Holding.created_at)).scalar()
    goals_last = db.query(func.max(GoalSnapshot.snapshot_date)).scalar()
    insights_last = db.query(func.max(ClaudeInsight.insight_date)).scalar()

    row = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    db_size_mb = round(row / (1024 * 1024), 1) if row else None

    return {
        "plaid_last_sync": plaid_last.isoformat() if plaid_last else None,
        "schwab_last_sync": schwab_last.isoformat() if schwab_last else None,
        "goals_last_snapshot": str(goals_last) if goals_last else None,
        "insights_last_generated": str(insights_last) if insights_last else None,
        "db_size_mb": db_size_mb,
    }


@router.get("/reauth-status")
def get_reauth_status(db: Session = Depends(get_db)):
    """Check whether any data source needs re-authentication."""
    issues: list[str] = []
    now = datetime.now(timezone.utc)

    # Plaid reauth events in last 7 days
    plaid_reauth = (
        db.query(NatebotEvent)
        .filter(
            NatebotEvent.event_type.ilike("%reauth%"),
            NatebotEvent.timestamp >= now - timedelta(days=7),
        )
        .first()
    )
    plaid_reauth_needed = plaid_reauth is not None
    if plaid_reauth_needed:
        issues.append(f"Plaid reauth event on {plaid_reauth.timestamp.isoformat()}")

    # Schwab: flag if last sync >48h old
    schwab_last = db.query(func.max(Holding.created_at)).scalar()
    schwab_reauth_needed = False
    if schwab_last is None:
        schwab_reauth_needed = True
        issues.append("No Schwab sync data found — token may be invalid")
    else:
        ts = schwab_last if schwab_last.tzinfo else schwab_last.replace(tzinfo=timezone.utc)
        if now - ts > timedelta(hours=48):
            schwab_reauth_needed = True
            issues.append(f"Schwab last sync stale ({ts.isoformat()}) — token may need refresh")

    return {
        "plaid_reauth_needed": plaid_reauth_needed,
        "schwab_reauth_needed": schwab_reauth_needed,
        "issues": issues,
    }


@router.post("/run-jobs")
def trigger_all_jobs(_: dict = Depends(require_auth)):
    """Trigger all cron jobs immediately via the cron container's trigger server."""
    try:
        resp = httpx.post("http://finforge-cron:9090/run-all", timeout=10)
        if resp.is_success:
            return {"status": "triggered", "detail": "All cron jobs started"}
        logger.error("Cron trigger returned HTTP %d", resp.status_code)
        raise HTTPException(status_code=502, detail="Cron trigger failed")
    except httpx.ConnectError:
        logger.error("Cannot reach cron trigger server")
        raise HTTPException(status_code=502, detail="Cron container unreachable")
    except Exception as exc:
        logger.error("Cron trigger error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/cron-logs")
def get_cron_logs(
    job: str | None = None,
    level: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Fetch recent cron log entries with optional filters."""
    q = db.query(CronLog).order_by(CronLog.created_at.desc())
    if job:
        q = q.filter(CronLog.job_name == job)
    if level:
        q = q.filter(CronLog.level == level.upper())
    rows = q.limit(min(limit, 1000)).all()
    return {
        "logs": [
            {
                "id": str(r.id),
                "job_name": r.job_name,
                "level": r.level,
                "message": r.message,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": len(rows),
    }
