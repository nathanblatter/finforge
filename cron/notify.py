"""Helper to queue iMessage notifications for NateBot delivery."""

import logging
import uuid
from datetime import datetime, timezone

from db import NatebotQueueRow, get_session

logger = logging.getLogger(__name__)

MAX_IMESSAGE_LENGTH = 1600


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
