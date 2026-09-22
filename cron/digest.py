"""Weekly email digest for FinForge cron.

Assembles a week-over-week financial summary (net worth delta, top spend
categories, goal progress, open alerts), has Claude write a short narrative,
and emails it through the local Postfix relay.
"""

import logging
import smtplib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage

import anthropic
from sqlalchemy import desc

from config import settings
from db import (
    AccountRow,
    BalanceRow,
    GoalAlertRow,
    GoalRow,
    GoalSnapshotRow,
    NotificationRow,
    TransactionRow,
    get_session,
)

logger = logging.getLogger("finforge.cron.digest")

# Mirror the report email settings (local Postfix relay, no auth).
_SMTP_HOST = "docker-services-postfix-1"
_SMTP_PORT = 25
_FROM_ADDR = "noreply@nathanblatter.com"
_TO_ADDR = settings.report_to_email


# ---------------------------------------------------------------------------
# Fact assembly
# ---------------------------------------------------------------------------

def _net_worth_as_of(session, accounts, as_of: date | None) -> Decimal:
    """Net worth from each account's latest balance on/before `as_of` (or latest)."""
    total = Decimal("0")
    for acct in accounts:
        q = session.query(BalanceRow).filter(BalanceRow.account_id == acct.id)
        if as_of is not None:
            q = q.filter(BalanceRow.balance_date <= as_of)
        bal = q.order_by(desc(BalanceRow.balance_date)).first()
        if bal is None:
            continue
        amt = bal.balance_amount
        if acct.account_type == "credit_card":
            total -= abs(amt)
        else:
            total += amt
    return total


def _gather_facts(session) -> dict:
    today = date.today()
    week_ago = today - timedelta(days=7)
    accounts = session.query(AccountRow).filter_by(is_active=True).all()

    net_now = _net_worth_as_of(session, accounts, None)
    net_prev = _net_worth_as_of(session, accounts, week_ago)

    # Top spend categories over the last 7 days (non-pending debits).
    txns = (
        session.query(TransactionRow)
        .filter(
            TransactionRow.date >= week_ago,
            TransactionRow.is_pending.is_(False),
            TransactionRow.amount > 0,
        )
        .all()
    )
    cat_totals: dict[str, Decimal] = {}
    week_spend = Decimal("0")
    for t in txns:
        cat = t.category or "Uncategorized"
        cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + t.amount
        week_spend += t.amount
    top_categories = sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]

    # Active goals with latest progress.
    goals = session.query(GoalRow).filter_by(status="active").all()
    goal_lines: list[str] = []
    for g in goals:
        snap = (
            session.query(GoalSnapshotRow)
            .filter_by(goal_id=g.id)
            .order_by(desc(GoalSnapshotRow.snapshot_date))
            .first()
        )
        if snap is not None:
            pct = float(snap.pct_complete)
            label = "On Track" if pct >= 90 else ("At Risk" if pct >= 70 else "Off Track")
            goal_lines.append(f"{g.name}: {pct:.0f}% ({label})")
        else:
            goal_lines.append(f"{g.name}: no data")

    # Open (unacknowledged) alerts.
    open_goal_alerts = session.query(GoalAlertRow).filter(GoalAlertRow.is_acknowledged.is_(False)).count()
    open_notes = session.query(NotificationRow).filter(NotificationRow.is_acknowledged.is_(False)).count()

    return {
        "net_now": net_now,
        "net_delta": net_now - net_prev,
        "week_spend": week_spend,
        "top_categories": top_categories,
        "goal_lines": goal_lines,
        "open_alerts": open_goal_alerts + open_notes,
        "txn_count": len(txns),
    }


def _facts_text(f: dict) -> str:
    delta = f["net_delta"]
    sign = "+" if delta >= 0 else "-"
    lines = [
        f"Net worth: ${float(f['net_now']):,.2f} ({sign}${abs(float(delta)):,.2f} this week)",
        f"Spending (last 7 days): ${float(f['week_spend']):,.2f} across {f['txn_count']} transactions",
        "",
        "Top categories:",
    ]
    if f["top_categories"]:
        for cat, amt in f["top_categories"]:
            lines.append(f"  - {cat}: ${float(amt):,.2f}")
    else:
        lines.append("  (no spending recorded)")
    lines.append("")
    lines.append("Active goals:")
    if f["goal_lines"]:
        lines += [f"  - {g}" for g in f["goal_lines"]]
    else:
        lines.append("  (no active goals)")
    lines.append("")
    lines.append(f"Open alerts: {f['open_alerts']}")
    return "\n".join(lines)


def _claude_narrative(facts_text: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=350,
            system=(
                "You are FinForge, a personal finance assistant. Write a short, friendly "
                "weekly summary (3-4 sentences) for the user based on the data provided. "
                "Highlight what changed and one practical suggestion. Be specific with numbers. "
                "Do not use markdown or a greeting/sign-off — just the paragraph."
            ),
            messages=[{"role": "user", "content": f"This week's data:\n\n{facts_text}"}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.error("[digest] Claude narrative failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_weekly_digest() -> None:
    """Build and send the weekly digest email."""
    with get_session() as session:
        facts = _gather_facts(session)

    facts_text = _facts_text(facts)
    narrative = _claude_narrative(facts_text)

    body_parts = []
    if narrative:
        body_parts.append(narrative)
        body_parts.append("")
        body_parts.append("-" * 40)
        body_parts.append("")
    body_parts.append(facts_text)
    body = "\n".join(body_parts)

    msg = EmailMessage()
    msg["Subject"] = f"FinForge Weekly Digest — {date.today():%b %d, %Y}"
    msg["From"] = _FROM_ADDR
    msg["To"] = _TO_ADDR
    msg.set_content(body)

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(msg)
        logger.info("[digest] Weekly digest sent to %s", _TO_ADDR)
    except Exception as exc:
        logger.error("[digest] Failed to send weekly digest: %s", exc)
        raise
