"""Budget and price-alert evaluation for FinForge cron.

Writes generic Notification rows (surfaced on the Alerts page) and queues
NateBot iMessage notifications when thresholds are crossed.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import extract

from db import (
    BudgetRow,
    MarketDataCacheRow,
    NotificationRow,
    PriceAlertRow,
    TransactionRow,
    get_session,
)

logger = logging.getLogger("finforge.cron.alerts_engine")

BUDGET_WARNING_PCT = 80.0


def _add_notification(session, source: str, title: str, alert_type: str, message: str) -> None:
    session.add(NotificationRow(
        id=uuid.uuid4(),
        source=source,
        title=title,
        alert_type=alert_type,
        message=message,
        is_acknowledged=False,
        acknowledged_at=None,
        created_at=datetime.now(timezone.utc),
    ))


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def run_check_budget_alerts() -> None:
    """Compute this month's spend per budget; notify on 80% and 100% crossings."""
    today = date.today()

    with get_session() as session:
        budgets = session.query(BudgetRow).all()
        logger.info("check_budget_alerts: evaluating %d budget(s)", len(budgets))

        created = 0
        for b in budgets:
            rows = (
                session.query(TransactionRow.amount)
                .filter(
                    TransactionRow.category == b.category,
                    TransactionRow.is_pending.is_(False),
                    extract("year", TransactionRow.date) == today.year,
                    extract("month", TransactionRow.date) == today.month,
                )
                .all()
            )
            spent = sum((r[0] for r in rows if r[0] and r[0] > 0), Decimal("0"))
            limit = Decimal(b.monthly_limit)
            if limit <= 0:
                continue
            pct = float(spent / limit * 100)

            if pct >= 100:
                alert_type = "budget_exceeded"
                message = (
                    f"Budget for {b.category} exceeded: ${float(spent):,.2f} of "
                    f"${float(limit):,.2f} ({pct:.0f}%) this month."
                )
            elif pct >= BUDGET_WARNING_PCT:
                alert_type = "budget_warning"
                message = (
                    f"Budget for {b.category} at {pct:.0f}%: ${float(spent):,.2f} of "
                    f"${float(limit):,.2f} this month."
                )
            else:
                continue

            # Dedup: skip if an unacknowledged alert of the same type already exists.
            existing = (
                session.query(NotificationRow)
                .filter(
                    NotificationRow.source == "budget",
                    NotificationRow.title == b.category,
                    NotificationRow.alert_type == alert_type,
                    NotificationRow.is_acknowledged.is_(False),
                )
                .first()
            )
            if existing is not None:
                continue

            _add_notification(session, "budget", b.category, alert_type, message)
            created += 1
            try:
                from notify import queue_notification
                emoji = "🔴" if alert_type == "budget_exceeded" else "⚠️"
                queue_notification("budget_alert", f"{emoji} {message}", priority="normal")
            except Exception:
                pass

        logger.info("check_budget_alerts: %d new alert(s) created", created)


# ---------------------------------------------------------------------------
# Price alerts
# ---------------------------------------------------------------------------

def run_check_price_alerts() -> None:
    """Compare active price alerts to the latest cached quote; fire one-shot."""
    with get_session() as session:
        alerts = session.query(PriceAlertRow).filter(PriceAlertRow.is_active.is_(True)).all()
        if not alerts:
            return
        logger.info("check_price_alerts: evaluating %d active alert(s)", len(alerts))

        symbols = {a.symbol for a in alerts}
        cache_rows = (
            session.query(MarketDataCacheRow)
            .filter(MarketDataCacheRow.symbol.in_(symbols))
            .all()
        )
        price_map = {r.symbol: r.last_price for r in cache_rows}

        fired = 0
        for a in alerts:
            price = price_map.get(a.symbol)
            if price is None:
                continue
            threshold = Decimal(a.threshold)
            crossed = (
                (a.direction == "above" and price >= threshold)
                or (a.direction == "below" and price <= threshold)
            )
            if not crossed:
                continue

            arrow = "≥" if a.direction == "above" else "≤"
            message = f"{a.symbol} is {arrow} ${float(threshold):,.2f} — now ${float(price):,.2f}."
            _add_notification(session, "price", a.symbol, f"price_{a.direction}", message)

            # One-shot: deactivate so it doesn't re-fire every cycle.
            a.is_active = False
            a.last_triggered_at = datetime.now(timezone.utc)
            fired += 1

            try:
                from notify import queue_notification
                queue_notification("price_alert", f"📈 {message}", priority="normal")
            except Exception:
                pass

        logger.info("check_price_alerts: %d alert(s) fired", fired)
