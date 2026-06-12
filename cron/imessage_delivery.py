"""Deliver queued NateBot notifications as real iMessages.

FinForge enqueues outbound alerts (goal/budget/price) into natebot_queue.
This job flushes that queue by POSTing each message to the imessage-api
gateway (`POST /send`) and marking it delivered. Idempotent: only undelivered
rows are sent, and a row is marked delivered only after a successful send.
"""

import logging
from datetime import datetime, timezone

import httpx

from config import settings
from db import NatebotQueueRow, get_session

logger = logging.getLogger("finforge.cron.imessage")

# Send oldest-first; cap per run so a backlog can't hammer the gateway.
BATCH_SIZE = 20


def deliver_pending_notifications() -> None:
    """Send all undelivered queue rows via the imessage-api gateway."""
    if not settings.imessage_api_key or not settings.imessage_recipient:
        logger.debug("[imessage] gateway not configured (key/recipient) — skipping")
        return

    url = settings.imessage_api_url.rstrip("/") + "/send"
    headers = {"X-API-Key": settings.imessage_api_key, "Content-Type": "application/json"}

    with get_session() as session:
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
