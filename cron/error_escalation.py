"""Escalate persistent cron job failures to an iMessage (finforge-32).

Every scheduled job swallows its own exceptions into cron_logs, so a job can
fail every run forever with no operator signal (proven by the Aug 2026 Schwab
outage: 609 ERROR rows over 5 days, zero alerts). This job is the missing
watchdog: it scans cron_logs for jobs that keep erroring and queues one
high-priority NateBot notification per job per ESCALATION_COOLDOWN_HOURS.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from db import get_session
from notify import queue_notification

logger = logging.getLogger("finforge.cron.error_escalation")

LOOKBACK_HOURS = 3          # window scanned for repeated failures
MIN_ERRORS_TO_ESCALATE = 3  # distinct ERROR/CRITICAL rows for one job in the window
ESCALATION_COOLDOWN_HOURS = 12
ESCALATION_CATEGORY_PREFIX = "cron_errors"

# error_escalation writes cron_logs rows itself; never escalate about them.
IGNORED_JOBS = {"error_escalation"}


def run_error_escalation() -> None:
    from db import CronLogRow, NatebotQueueRow

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=LOOKBACK_HOURS)
    cooldown_start = now - timedelta(hours=ESCALATION_COOLDOWN_HOURS)

    with get_session() as session:
        rows = (
            session.query(
                CronLogRow.job_name,
                func.count(CronLogRow.id),
                func.max(CronLogRow.message),
            )
            .filter(
                CronLogRow.level.in_(("ERROR", "CRITICAL")),
                CronLogRow.created_at >= window_start,
            )
            .group_by(CronLogRow.job_name)
            .all()
        )

        for job_name, error_count, sample_message in rows:
            if job_name in IGNORED_JOBS or error_count < MIN_ERRORS_TO_ESCALATE:
                continue

            category = f"{ESCALATION_CATEGORY_PREFIX}:{job_name}"
            already_sent = (
                session.query(NatebotQueueRow)
                .filter(
                    NatebotQueueRow.category == category,
                    NatebotQueueRow.created_at >= cooldown_start,
                )
                .first()
            )
            if already_sent is not None:
                continue

            queue_notification(
                category=category,
                text=(
                    f"FinForge: cron job '{job_name}' has failed {error_count}x "
                    f"in the last {LOOKBACK_HOURS}h and is still failing.\n\n"
                    f"Latest: {str(sample_message)[:300]}\n\n"
                    "Check the System page or: docker exec docker-services-postgres-1 "
                    f"psql -U postgres -d finforge -c \"SELECT created_at, level, message FROM cron_logs "
                    f"WHERE job_name='{job_name}' ORDER BY created_at DESC LIMIT 10;\""
                ),
                priority="high",
            )
            logger.warning(
                "[error_escalation] Escalated %s (%d errors in %dh)",
                job_name, error_count, LOOKBACK_HOURS,
            )
