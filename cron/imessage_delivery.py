"""Deliver queued NateBot notifications as real iMessages.

FinForge enqueues outbound alerts (goal/budget/price) into natebot_queue.
This job flushes that queue by POSTing each message to the imessage-api
gateway (`POST /send`) and marking it delivered. Idempotent: only undelivered
rows are sent, and a row is marked delivered only after a successful send.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from config import settings
from db import NatebotQueueRow, get_session

logger = logging.getLogger("finforge.cron.imessage")

# Send oldest-first; cap per run so a backlog can't hammer the gateway.
BATCH_SIZE = 20
# Drop (don't send) anything older than this — prevents a stale backlog from
# blasting all at once if the gateway was unreachable for a while.
MAX_AGE_MINUTES = 120


def deliver_pending_notifications() -> None:
    """Send all undelivered queue rows via the imessage-api gateway."""
    if not settings.imessage_api_key or not settings.imessage_recipient:
        logger.debug("[imessage] gateway not configured (key/recipient) — skipping")
        return

    url = settings.imessage_api_url.rstrip("/") + "/send"
    headers = {"X-API-Key": settings.imessage_api_key, "Content-Type": "application/json"}

    with get_session() as session:
        # Suppress stale messages instead of delivering them late. Urgent
        # messages are exempt: a late urgent alert (drawdown, runway floor,
        # dead Schwab auth) still beats a silently dropped one (finforge-32).
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=MAX_AGE_MINUTES)
        dropped = (
            session.query(NatebotQueueRow)
            .filter(
                NatebotQueueRow.delivered.is_(False),
                NatebotQueueRow.created_at < stale_cutoff,
                NatebotQueueRow.priority != "urgent",
            )
            .update(
                {NatebotQueueRow.delivered: True, NatebotQueueRow.delivered_at: datetime.now(timezone.utc)},
                synchronize_session=False,
            )
        )
        if dropped:
            logger.info("[imessage] suppressed %d stale message(s) (>%dm old)", dropped, MAX_AGE_MINUTES)

        rows = (
            session.query(NatebotQueueRow)
            .filter(NatebotQueueRow.delivered.is_(False))
            .order_by(NatebotQueueRow.created_at)
            .limit(BATCH_SIZE)
            .all()
        )
        if not rows:
            return

        sent = 0
        with httpx.Client(timeout=10) as client:
            for row in rows:
                try:
                    resp = client.post(
                        url,
                        headers=headers,
                        json={"recipient": settings.imessage_recipient, "message": row.text},
                    )
                    if resp.status_code == 200 and resp.json().get("status") == "sent":
                        row.delivered = True
                        row.delivered_at = datetime.now(timezone.utc)
                        sent += 1
                    else:
                        # Leave undelivered so it retries next run.
                        logger.warning("[imessage] send failed (HTTP %s): %s", resp.status_code, resp.text[:200])
                        break  # gateway problem — stop; retry whole batch next cycle
                except Exception as exc:
                    logger.error("[imessage] delivery error: %s", exc)
                    break

        logger.info("[imessage] delivered %d/%d queued message(s)", sent, len(rows))
