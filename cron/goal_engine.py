"""Goal snapshot computation and alert evaluation for FinForge cron."""

import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from db import (
    AccountRow,
    BalanceRow,
    GoalAlertRow,
    GoalRow,
    GoalSnapshotRow,
    TransactionRow,
    get_session,
)

logger = logging.getLogger("finforge.cron.goal_engine")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_metric_value(session: Session, goal: GoalRow) -> Optional[Decimal]:
    """Parse goal.metric_source and return the current Decimal value, or None."""
    if not goal.metric_source:
        return None

    try:
        source = json.loads(goal.metric_source)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Goal %s has unparseable metric_source: %r", goal.id, goal.metric_source)
        return None

    goal_type = goal.goal_type

    # ------------------------------------------------------------------
    # balance_target — sum latest balances for a list of account aliases
    # ------------------------------------------------------------------
    if goal_type == "balance_target":
        aliases: list[str] = source.get("aliases", [])
        if not aliases:
            return None

        total = Decimal("0")
        for alias in aliases:
            account = (
                session.query(AccountRow)
                .filter(AccountRow.alias == alias, AccountRow.is_active.is_(True))
                .first()
            )
            if account is None:
                logger.debug("balance_target: account alias %r not found, skipping", alias)
                continue

            latest_balance = (
                session.query(BalanceRow)
                .filter(BalanceRow.account_id == account.id)
                .order_by(desc(BalanceRow.balance_date))
                .first()
            )
            if latest_balance is None:
                continue

            amount = latest_balance.balance_amount
            # Credit card balances are stored as negative; use absolute value
            if account.account_type == "credit_card":
                amount = abs(amount)
            total += amount

        return total

    # ------------------------------------------------------------------
    # spend_limit — sum transactions for categories in a given month
    # ------------------------------------------------------------------
    elif goal_type == "spend_limit":
        categories: list[str] = source.get("categories", [])
        month_str: Optional[str] = source.get("month")  # "YYYY-MM" or null

        if not categories:
            return None

        today = date.today()
        if month_str:
            try:
                year, month = int(month_str[:4]), int(month_str[5:7])
            except (ValueError, IndexError):
                logger.warning("spend_limit: invalid month format %r for goal %s", month_str, goal.id)
                year, month = today.year, today.month
        else:
            year, month = today.year, today.month

        from sqlalchemy import extract

        rows = (
            session.query(TransactionRow)
            .join(AccountRow, TransactionRow.account_id == AccountRow.id)
            .filter(
                TransactionRow.category.in_(categories),
                TransactionRow.is_fixed_expense.is_(False),
                TransactionRow.is_pending.is_(False),
                extract("year", TransactionRow.date) == year,
                extract("month", TransactionRow.date) == month,
            )
            .all()
        )

        # Plaid returns spending as positive amounts for debits
        total = sum((r.amount for r in rows if r.amount > 0), Decimal("0"))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # contribution_rate — latest portfolio balance for an IRA account
    # ------------------------------------------------------------------
    elif goal_type == "contribution_rate":
        alias: str = source.get("alias", "")
        if not alias:
            return None

        account = (
            session.query(AccountRow)
            .filter(AccountRow.alias == alias, AccountRow.is_active.is_(True))
            .first()
        )
        if account is None:
            logger.debug("contribution_rate: account alias %r not found", alias)
            return None

        latest_balance = (
            session.query(BalanceRow)
            .filter(
                BalanceRow.account_id == account.id,
                BalanceRow.balance_type == "portfolio_value",
            )
            .order_by(desc(BalanceRow.balance_date))
            .first()
        )
        if latest_balance is None:
            return None

        return latest_balance.balance_amount

    # ------------------------------------------------------------------
    # portfolio_growth — latest balance for a brokerage account
    # ------------------------------------------------------------------
    elif goal_type == "portfolio_growth":
        alias = source.get("alias", "")
        if not alias:
            return None

        account = (
            session.query(AccountRow)
            .filter(AccountRow.alias == alias, AccountRow.is_active.is_(True))
            .first()
        )
        if account is None:
            logger.debug("portfolio_growth: account alias %r not found", alias)
            return None

        latest_balance = (
            session.query(BalanceRow)
            .filter(BalanceRow.account_id == account.id)
            .order_by(desc(BalanceRow.balance_date))
            .first()
        )
        if latest_balance is None:
            return None

        return latest_balance.balance_amount

    # ------------------------------------------------------------------
    # custom — cannot auto-compute
    # ------------------------------------------------------------------
    elif goal_type == "custom":
        return None

    logger.warning("Goal %s has unrecognised goal_type %r", goal.id, goal_type)
    return None


def _compute_pct_complete(goal: GoalRow, current_value: Decimal) -> Decimal:
    """Compute percentage-complete (0–100) for a goal given its current value."""
    target = Decimal(str(goal.target_value))
    if target == 0:
        return Decimal("100.00")

    if goal.direction == "increase":
        raw = current_value / target * 100
        pct = min(raw, Decimal("100"))

    elif goal.direction == "decrease":
        # Goal is to drive the value DOWN to target; 100% means fully achieved
        raw = (1 - current_value / target) * 100
        pct = max(raw, Decimal("0"))

    elif goal.direction == "maintain":
        # Within 10% of target counts as fully on-track
        deviation = abs(current_value - target) / target * 100
        pct = Decimal("100") if deviation <= 10 else Decimal("50")

    else:
        pct = Decimal("0")

    return pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Public job functions
# ---------------------------------------------------------------------------

def run_generate_goal_snapshots() -> None:
    """Compute and persist today's progress snapshot for every active goal."""
    today = date.today()

    with get_session() as session:
        active_goals = session.query(GoalRow).filter(GoalRow.status == "active").all()
        logger.info("generate_goal_snapshots: found %d active goal(s)", len(active_goals))

        for goal in active_goals:
            current_value = _resolve_metric_value(session, goal)
            if current_value is None:
                logger.debug(
                    "generate_goal_snapshots: skipping goal %s (%r) — metric resolved None",
                    goal.id, goal.name,
                )
                continue

            pct_complete = _compute_pct_complete(goal, current_value)

            # Upsert: update existing snapshot for today, or insert a new one
            existing = (
                session.query(GoalSnapshotRow)
                .filter(
                    GoalSnapshotRow.goal_id == goal.id,
                    GoalSnapshotRow.snapshot_date == today,
                )
                .first()
            )

            if existing is not None:
                existing.current_value = current_value
                existing.target_value = goal.target_value
                existing.pct_complete = pct_complete
                logger.info(
                    "generate_goal_snapshots: updated snapshot for goal %r — "
                    "current=%.2f target=%.2f pct=%.2f%%",
                    goal.name, current_value, goal.target_value, pct_complete,
                )
            else:
                session.add(GoalSnapshotRow(
                    id=uuid.uuid4(),
                    goal_id=goal.id,
                    snapshot_date=today,
                    current_value=current_value,
                    target_value=goal.target_value,
                    pct_complete=pct_complete,
                    created_at=datetime.now(tz=timezone.utc),
                ))
                logger.info(
                    "generate_goal_snapshots: inserted snapshot for goal %r — "
                    "current=%.2f target=%.2f pct=%.2f%%",
                    goal.name, current_value, goal.target_value, pct_complete,
                )


def run_check_goal_alerts() -> None:
    """Evaluate alert thresholds for every active goal and create GoalAlert rows."""
    with get_session() as session:
        active_goals = session.query(GoalRow).filter(GoalRow.status == "active").all()
        logger.info("check_goal_alerts: evaluating %d active goal(s)", len(active_goals))

        alerts_created = 0
        for goal in active_goals:
            latest = (
                session.query(GoalSnapshotRow)
                .filter(GoalSnapshotRow.goal_id == goal.id)
                .order_by(desc(GoalSnapshotRow.snapshot_date))
                .first()
            )
            if latest is None:
                logger.debug("check_goal_alerts: no snapshot for goal %r, skipping", goal.name)
                continue

            pct = float(latest.pct_complete)

            if pct >= 100:
                alert_type = "completed"
                message = (
                    f"Goal '{goal.name}' is complete! "
                    f"Current value {latest.current_value} reached "
                    f"target {latest.target_value} ({pct:.1f}%)."
                )
            elif pct >= 90:
                continue  # On Track — no alert
            elif pct >= 70:
                alert_type = "at_risk"
                message = (
                    f"Goal '{goal.name}' is at risk ({pct:.1f}%). "
                    f"Current: {latest.current_value}, target: {latest.target_value}."
                )
            else:
                alert_type = "off_track"
                message = (
                    f"Goal '{goal.name}' is off track ({pct:.1f}%). "
                    f"Current: {latest.current_value}, target: {latest.target_value}."
                )

            # Dedup: skip if unacknowledged alert of same type already exists
            existing = (
                session.query(GoalAlertRow)
                .filter(
                    GoalAlertRow.goal_id == goal.id,
                    GoalAlertRow.alert_type == alert_type,
                    GoalAlertRow.is_acknowledged.is_(False),
                )
                .first()
            )
            if existing is not None:
                logger.debug(
                    "check_goal_alerts: unack'd %r alert exists for goal %r, skipping",
                    alert_type, goal.name,
                )
                continue

            session.add(GoalAlertRow(
                id=uuid.uuid4(),
                goal_id=goal.id,
                alert_type=alert_type,
                message=message,
                is_acknowledged=False,
                acknowledged_at=None,
                created_at=datetime.now(tz=timezone.utc),
            ))
            alerts_created += 1
            logger.info(
                "check_goal_alerts: created %r alert for goal %r (pct=%.1f%%)",
                alert_type, goal.name, pct,
            )

            # Queue iMessage notification
            try:
                from notify import queue_notification
                emoji = "✅" if alert_type == "completed" else "⚠️" if alert_type == "at_risk" else "🔴"
                queue_notification("goal_alert", f"{emoji} {message}", priority="normal")
            except Exception:
                pass

        logger.info("check_goal_alerts: %d new alert(s) created", alerts_created)
