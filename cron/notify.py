"""Helper to queue iMessage notifications for NateBot delivery."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from db import NatebotQueueRow, get_session

logger = logging.getLogger(__name__)

MAX_IMESSAGE_LENGTH = 1600

SCHWAB_REAUTH_CATEGORY = "schwab_reauth"
SCHWAB_REAUTH_DEDUPE_HOURS = 12


def alert_schwab_reauth(source: str) -> None:
    """Queue an urgent iMessage that Schwab auth is dead, with the exact fix.

    Dedupes against natebot_queue (one alert per SCHWAB_REAUTH_DEDUPE_HOURS,
    surviving restarts) so watchdog/sync paths can call this unconditionally.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=SCHWAB_REAUTH_DEDUPE_HOURS)
        with get_session() as session:
            recent = (
                session.query(NatebotQueueRow)
                .filter(
                    NatebotQueueRow.category == SCHWAB_REAUTH_CATEGORY,
                    NatebotQueueRow.created_at >= cutoff,
                )
                .first()
            )
            if recent is not None:
                logger.info(
                    "[notify] Schwab reauth alert suppressed (already sent within %dh)",
                    SCHWAB_REAUTH_DEDUPE_HOURS,
                )
                return
    except Exception as exc:
        logger.error("[notify] Schwab reauth dedupe check failed (%s) — sending anyway", exc)

    queue_notification(
        category=SCHWAB_REAUTH_CATEGORY,
        text=(
            "FinForge: Schwab auth is DEAD — portfolio/tax/dividend syncs are stopped "
            f"({source}).\n\nFix: cd ~/dev/finforge && python3 scripts/schwab_reauth.py"
        ),
        priority="urgent",
    )


def queue_notification(category: str, text: str, priority: str = "normal") -> None:
    """Insert a notification into natebot_queue for NateBot to pick up."""
    # Split long messages
    if len(text) <= MAX_IMESSAGE_LENGTH:
        chunks = [text]
    else:
        chunks = []
        lines = text.split("\n")
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > MAX_IMESSAGE_LENGTH:
                chunks.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.strip())

    try:
        with get_session() as session:
            for chunk in chunks:
                session.add(NatebotQueueRow(
                    id=uuid.uuid4(),
                    priority=priority,
                    category=category,
                    text=chunk,
                    delivered=False,
                    created_at=datetime.now(timezone.utc),
                ))
        logger.info("[notify] Queued %d message(s) for category=%s", len(chunks), category)
    except Exception as exc:
        logger.error("[notify] Failed to queue notification: %s", exc)
