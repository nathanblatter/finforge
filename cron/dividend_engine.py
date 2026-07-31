"""Dividend & income calendar engine for FinForge cron (finforge-5).

Two responsibilities, both operating on dividend_transactions rows written by
cron/integrations/schwab_sync.py:

1. Backfill metadata: quantity held at payment time (from the nearest holdings
   snapshot), the resulting per-share amount, and DRIP linkage (a same-symbol
   BUY transaction shortly after the dividend, close in dollar amount).
2. Raise/cut detection: compare each holding's latest per-share dividend to
   its prior payment and fire a Notification + NateBot alert on a meaningful
   change (raise = normal priority, cut = urgent), following the same
   dedup-by-unacknowledged / dedup-by-message-tag conventions used in
   alerts_engine.py.
"""

import logging
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from db import DividendTransactionRow, HoldingRow, NotificationRow, TransactionRow, get_session

logger = logging.getLogger("finforge.cron.dividend_engine")

# DRIP matching: a same-symbol BUY within this many days of the dividend,
# whose dollar amount is within this tolerance of the dividend cash amount.
DRIP_MATCH_WINDOW_DAYS = 3
DRIP_AMOUNT_TOLERANCE_PCT = 0.08

# Raise/cut detection
MIN_HISTORY_FOR_CHANGE_ALERT = 2
CHANGE_THRESHOLD_PCT = 1.0  # ignore sub-1% differences (rounding noise)


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
# Metadata backfill: quantity / per-share amount / DRIP linkage
# ---------------------------------------------------------------------------

def run_link_dividend_metadata() -> None:
    """Backfill per-share amount and DRIP linkage for dividend rows that
    don't have it yet (i.e. new rows written by the most recent sync)."""
    with get_session() as session:
        pending = (
            session.query(DividendTransactionRow)
            .filter(DividendTransactionRow.per_share_amount.is_(None))
            .all()
        )
        linked = 0
        drip_matched = 0

        for d in pending:
            # Nearest holdings snapshot at or before the payment date tells us
            # how many shares were held when the dividend was paid.
            snap = (
                session.query(HoldingRow)
                .filter(
                    HoldingRow.account_id == d.account_id,
                    HoldingRow.symbol == d.symbol,
                    HoldingRow.snapshot_date <= d.pay_date,
                )
                .order_by(HoldingRow.snapshot_date.desc())
                .first()
            )
            if snap is None:
                # Position may have been opened after the dividend's pay_date
                # relative to our first holdings snapshot — fall back to the
                # earliest snapshot we have as a best-effort estimate.
                snap = (
                    session.query(HoldingRow)
                    .filter(HoldingRow.account_id == d.account_id, HoldingRow.symbol == d.symbol)
                    .order_by(HoldingRow.snapshot_date.asc())
                    .first()
                )

            if snap is not None and snap.quantity and snap.quantity > 0:
                try:
                    d.quantity_at_payment = snap.quantity
                    d.per_share_amount = (Decimal(d.amount) / Decimal(snap.quantity)).quantize(Decimal("0.000001"))
                    linked += 1
                except (InvalidOperation, ZeroDivisionError):
                    pass

            # DRIP detection: a BUY of the same symbol shortly after the
            # dividend, whose dollar amount is close to the dividend cash.
            if not d.is_reinvested:
                window_end = d.pay_date + timedelta(days=DRIP_MATCH_WINDOW_DAYS)
                candidates = (
                    session.query(TransactionRow)
                    .filter(
                        TransactionRow.account_id == d.account_id,
                        TransactionRow.merchant_name == d.symbol,
                        TransactionRow.category == "Investment Transfer",
                        TransactionRow.subcategory == "BUY",
                        TransactionRow.date >= d.pay_date,
                        TransactionRow.date <= window_end,
                    )
                    .all()
                )
                dividend_amt = float(d.amount)
                if dividend_amt > 0:
                    for c in candidates:
                        diff_pct = abs(float(c.amount) - dividend_amt) / dividend_amt
                        if diff_pct <= DRIP_AMOUNT_TOLERANCE_PCT:
                            d.is_reinvested = True
                            d.reinvest_transaction_id = c.id
                            d.reinvest_amount = c.amount
                            drip_matched += 1
                            break

        logger.info(
            "link_dividend_metadata: linked %d row(s), matched %d DRIP reinvestment(s)",
            linked, drip_matched,
        )


# ---------------------------------------------------------------------------
# Raise/cut detection
# ---------------------------------------------------------------------------

def run_detect_dividend_changes() -> None:
    """Compare each symbol's latest per-share dividend payment to its prior
    one; fire a raise/cut Notification + NateBot alert on a real change."""
    with get_session() as session:
        rows = (
            session.query(DividendTransactionRow)
            .filter(DividendTransactionRow.per_share_amount.isnot(None))
            .order_by(DividendTransactionRow.symbol, DividendTransactionRow.pay_date)
            .all()
        )

        by_symbol: dict[str, list[DividendTransactionRow]] = defaultdict(list)
        for r in rows:
            by_symbol[r.symbol].append(r)

        fired = 0
        for symbol, payments in by_symbol.items():
            if len(payments) < MIN_HISTORY_FOR_CHANGE_ALERT:
                continue

            latest = payments[-1]
            prior = payments[-2]
            try:
                prev_ps = Decimal(prior.per_share_amount)
                new_ps = Decimal(latest.per_share_amount)
            except (InvalidOperation, TypeError):
                continue
            if prev_ps <= 0:
                continue

            change_pct = float((new_ps - prev_ps) / prev_ps * 100)
            if abs(change_pct) < CHANGE_THRESHOLD_PCT:
                continue

            direction = "raise" if change_pct > 0 else "cut"
            alert_type = f"dividend_{direction}"
            price_tag = f"${float(new_ps):.4f}/share"

            # Dedup: skip if we've already alerted on this exact new rate for
            # this symbol (mirrors the subscription-hike dedup pattern).
            existing = (
                session.query(NotificationRow)
                .filter(
                    NotificationRow.source == "dividend",
                    NotificationRow.title == symbol,
                    NotificationRow.alert_type == alert_type,
                    NotificationRow.message.like(f"%{price_tag}%"),
                )
                .first()
            )
            if existing is not None:
                continue

            verb = "raised" if direction == "raise" else "cut"
            message = (
                f"{symbol} dividend {verb} from ${float(prev_ps):.4f} to {price_tag} "
                f"({change_pct:+.1f}%) — paid {latest.pay_date}."
            )
            _add_notification(session, "dividend", symbol, alert_type, message)
            fired += 1

            try:
                from notify import queue_notification
                emoji = "📈" if direction == "raise" else "🔻"
                priority = "urgent" if direction == "cut" else "normal"
                queue_notification("dividend_alert", f"{emoji} {message}", priority=priority)
            except Exception:
                pass

        logger.info("detect_dividend_changes: %d alert(s) fired", fired)


# ---------------------------------------------------------------------------
# Combined entry point (cron/main.py job)
# ---------------------------------------------------------------------------

def run_dividend_income_sync() -> None:
    """Backfill dividend metadata, then evaluate raise/cut alerts. Called
    after schwab_sync so new dividend_transactions rows exist first."""
    run_link_dividend_metadata()
    run_detect_dividend_changes()
