"""
Spending anomaly detection for FinForge cron.

Two detectors over recent (last 14 days, non-pending) debit transactions:
  1. Category outliers — robust z-score (median/MAD) of the amount against
     the category's last 6 months of history.
  2. Duplicate charges — same merchant and same amount within 2 days.

Flagged transactions are written to spending_anomalies (one row per
transaction, ever), surfaced as Notifications, and queued for NateBot.
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np

from db import NotificationRow, SpendingAnomalyRow, TransactionRow, get_session

logger = logging.getLogger("finforge.cron.spending_anomalies")

RECENT_DAYS = 14
HISTORY_MONTHS = 6
Z_THRESHOLD = 3.5
MIN_AMOUNT = Decimal("25")       # ignore small charges
MIN_CATEGORY_SAMPLES = 8         # need history to call something an outlier
DUPLICATE_WINDOW_DAYS = 2
SKIP_CATEGORIES = frozenset({"Investment Transfer"})


def _robust_z(amount: float, history: np.ndarray) -> tuple[float, float]:
    """(z_score, median) using median absolute deviation."""
    med = float(np.median(history))
    mad = float(np.median(np.abs(history - med)))
    scale = 1.4826 * mad
    if scale < 1.0:  # near-constant history — fall back to std with a floor
        scale = max(float(np.std(history)), 1.0)
    return (amount - med) / scale, med


def run_spending_anomalies() -> None:
    today = date.today()
    recent_cutoff = today - timedelta(days=RECENT_DAYS)
    history_cutoff = today - timedelta(days=HISTORY_MONTHS * 31)

    with get_session() as session:
        recent = (
            session.query(TransactionRow)
            .filter(
                TransactionRow.date >= recent_cutoff,
                TransactionRow.is_pending.is_(False),
                TransactionRow.amount > 0,
            )
            .all()
        )
        if not recent:
            logger.info("[spending_anomalies] No recent transactions — skipping")
            return

        # Already-flagged transaction ids (never re-flag)
        flagged_ids = {
            r[0] for r in session.query(SpendingAnomalyRow.transaction_id).all()
        }

        # Category history for the outlier detector
        history_rows = (
            session.query(TransactionRow.category, TransactionRow.amount)
            .filter(
                TransactionRow.date >= history_cutoff,
                TransactionRow.date < recent_cutoff,
                TransactionRow.is_pending.is_(False),
                TransactionRow.amount > 0,
            )
            .all()
        )
        history_by_cat: dict[str, list[float]] = {}
        for cat, amount in history_rows:
            history_by_cat.setdefault(cat or "Other", []).append(float(amount))

        new_anomalies: list[tuple[TransactionRow, str, float | None, float | None, str]] = []

        # --- Detector 1: category outliers ---
        for t in recent:
            if t.id in flagged_ids:
                continue
            cat = t.category or "Other"
            if cat in SKIP_CATEGORIES or t.amount < MIN_AMOUNT:
                continue
            hist = history_by_cat.get(cat, [])
            if len(hist) < MIN_CATEGORY_SAMPLES:
                continue
            z, med = _robust_z(float(t.amount), np.array(hist))
            if z >= Z_THRESHOLD:
                detail = (
                    f"${float(t.amount):,.2f} at {t.merchant_name or 'unknown'} is unusually large "
                    f"for {cat} (typical ${med:,.2f}, z={z:.1f})"
                )
                new_anomalies.append((t, "outlier", z, med, detail))
                flagged_ids.add(t.id)

        # Duplicate-charge detection retired here (finforge-21/finforge-35-F6):
        # charge_guardian.detect_duplicate_charges is the single source — it
        # normalizes merchants, excludes recurring merchants and Investment
        # Transfer rows, none of which this detector did (it double-notified
        # and false-alerted on same-amount stock buys).

        # --- Persist + notify ---
        now = datetime.now(timezone.utc)
        for t, reason, z, typical, detail in new_anomalies:
            session.add(SpendingAnomalyRow(
                id=uuid.uuid4(),
                transaction_id=t.id,
                reason=reason,
                z_score=Decimal(str(round(z, 2))) if z is not None else None,
                typical_amount=Decimal(str(round(typical, 2))) if typical is not None else None,
                detail=detail,
                is_dismissed=False,
                created_at=now,
            ))
            session.add(NotificationRow(
                id=uuid.uuid4(),
                source="anomaly",
                title=t.merchant_name or (t.category or "Transaction"),
                alert_type=f"spending_{reason}",
                message=detail,
                is_acknowledged=False,
                acknowledged_at=None,
                created_at=now,
            ))

        logger.info("[spending_anomalies] Flagged %d new anomalies", len(new_anomalies))

    if new_anomalies:
        try:
            from notify import queue_notification
            lines = ["🚨 Unusual Spending Detected"]
            for _t, _reason, _z, _typical, detail in new_anomalies[:8]:
                lines.append(f"  • {detail}")
            queue_notification("spending_anomaly", "\n".join(lines), priority="normal")
        except Exception:
            pass
