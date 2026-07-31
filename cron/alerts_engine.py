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
    CashflowSettingsRow,
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

            # Run-rate projection: flag a likely overspend before it happens
            # (only once we're far enough into the month for pace to mean something)
            import calendar
            days_in_month = calendar.monthrange(today.year, today.month)[1]
            projected = float(spent) * days_in_month / max(today.day, 1)

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
            elif today.day >= 10 and projected > float(limit):
                alert_type = "budget_projected"
                message = (
                    f"{b.category} is pacing to ${projected:,.2f} this month — "
                    f"over the ${float(limit):,.2f} budget (${float(spent):,.2f} spent so far)."
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


# ---------------------------------------------------------------------------
# Subscription price hikes
# ---------------------------------------------------------------------------

HIKE_MIN_PRIOR_CHARGES = 3
HIKE_MIN_INCREASE_ABS = 1.0     # dollars
HIKE_MIN_INCREASE_PCT = 0.03    # 3%
HIKE_PRIOR_CONSISTENCY = 0.20   # priors must vary < 20% to call it a "price"


def run_check_subscription_hikes() -> None:
    """Detect recurring merchants whose latest charge jumped above their
    historical price. Fires one notification per merchant per new price."""
    from datetime import timedelta
    from statistics import median

    today = date.today()
    since = today - timedelta(days=7 * 31)

    with get_session() as session:
        txns = (
            session.query(TransactionRow)
            .filter(
                TransactionRow.date >= since,
                TransactionRow.is_pending.is_(False),
                TransactionRow.merchant_name.isnot(None),
                TransactionRow.amount > 0,
            )
            .all()
        )

        groups: dict[str, list] = {}
        for t in txns:
            groups.setdefault(t.merchant_name.strip(), []).append(t)

        fired = 0
        for merchant, ts in groups.items():
            if len(ts) < HIKE_MIN_PRIOR_CHARGES + 1:
                continue
            ts.sort(key=lambda t: (t.date, t.created_at))
            latest = ts[-1]
            priors = ts[:-1]

            distinct_months = {(t.date.year, t.date.month) for t in priors}
            if len(distinct_months) < 3:
                continue

            prior_amounts = [float(t.amount) for t in priors]
            prior_med = median(prior_amounts)
            if prior_med <= 0:
                continue
            # Priors must look like a stable price, not variable spend
            spread = (max(prior_amounts) - min(prior_amounts)) / prior_med
            if spread > HIKE_PRIOR_CONSISTENCY:
                continue

            new_amount = float(latest.amount)
            increase = new_amount - prior_med
            if increase < max(HIKE_MIN_INCREASE_ABS, prior_med * HIKE_MIN_INCREASE_PCT):
                continue

            # One alert per merchant per new price — message carries the price
            price_tag = f"to ${new_amount:,.2f}"
            existing = (
                session.query(NotificationRow)
                .filter(
                    NotificationRow.source == "subscription",
                    NotificationRow.title == merchant,
                    NotificationRow.alert_type == "price_hike",
                    NotificationRow.message.like(f"%{price_tag}%"),
                )
                .first()
            )
            if existing is not None:
                continue

            message = (
                f"{merchant} went up {price_tag} from ${prior_med:,.2f} "
                f"(+${increase:,.2f}, {increase / prior_med * 100:.0f}%) on {latest.date}."
            )
            _add_notification(session, "subscription", merchant, "price_hike", message)
            fired += 1
            try:
                from notify import queue_notification
                queue_notification("subscription_hike", f"💸 {message}", priority="normal")
            except Exception:
                pass

        logger.info("check_subscription_hikes: %d hike alert(s) fired", fired)


# ---------------------------------------------------------------------------
# Cash-flow runway floor
# ---------------------------------------------------------------------------

RUNWAY_HORIZON_DAYS = 90


def run_check_cashflow_runway() -> None:
    """Project the checking balance out RUNWAY_HORIZON_DAYS and, if the
    conservative (low-band) projection is on track to cross the configured
    floor within the user's configured lead time, fire one alert stating the
    date and days of lead time. Re-fires only if the predicted crossing date
    changes (a fresh forecast run), mirroring the subscription-hike
    per-value dedup convention."""
    from cashflow_forecast import compute_runway

    with get_session() as session:
        settings = session.query(CashflowSettingsRow).order_by(CashflowSettingsRow.created_at.asc()).first()
        if settings is None:
            logger.info("check_cashflow_runway: no settings configured, skipping")
            return

        floor = float(settings.floor_amount)
        lead_time_days = settings.lead_time_days

        result = compute_runway(session, days=RUNWAY_HORIZON_DAYS)
        if result["checking_balance"] is None:
            logger.info("check_cashflow_runway: no checking balance data, skipping")
            return

        crossing_date = None
        for point in result["series"]:
            if point["low"] < floor:
                crossing_date = point["date"]
                break

        if crossing_date is None:
            logger.info("check_cashflow_runway: no floor crossing predicted within %d days", RUNWAY_HORIZON_DAYS)
            return

        today = date.today()
        lead_time_until_crossing = (crossing_date - today).days
        if lead_time_until_crossing > lead_time_days:
            logger.info(
                "check_cashflow_runway: crossing predicted %s but outside lead-time window (%d > %d)",
                crossing_date, lead_time_until_crossing, lead_time_days,
            )
            return

        date_tag = crossing_date.isoformat()
        existing = (
            session.query(NotificationRow)
            .filter(
                NotificationRow.source == "cashflow",
                NotificationRow.title == "Checking",
                NotificationRow.alert_type == "floor_risk",
                NotificationRow.message.like(f"%{date_tag}%"),
            )
            .first()
        )
        if existing is not None:
            logger.info("check_cashflow_runway: already alerted for crossing on %s", date_tag)
            return

        message = (
            f"Checking balance is projected to drop below your ${floor:,.2f} floor around "
            f"{date_tag} ({lead_time_until_crossing} day(s) from now)."
        )
        _add_notification(session, "cashflow", "Checking", "floor_risk", message)
        logger.info("check_cashflow_runway: alert created for crossing on %s", date_tag)
        try:
            from notify import queue_notification
            queue_notification("cashflow_runway", f"🪫 {message}", priority="high")
        except Exception:
            pass
