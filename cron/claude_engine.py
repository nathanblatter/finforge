"""Nightly Claude AI insight generation for FinForge cron."""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import anthropic
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import settings
from db import (
    AccountRow,
    BalanceRow,
    ClaudeInsightRow,
    GoalRow,
    GoalSnapshotRow,
    TransactionRow,
    get_session,
)

logger = logging.getLogger("finforge.cron.claude_engine")

_INSIGHT_PROMPTS: dict[str, str] = {
    "spending_pattern": (
        "Analyze my spending patterns from the last 30 days. "
        "Focus on category trends, notable changes, or spending habits worth highlighting."
    ),
    "goal_trajectory": (
        "Analyze my active goal progress. Identify which goals are on track, at risk, "
        "or need attention. Project outcomes if the current pace continues."
    ),
    "savings_opportunity": (
        "Identify savings opportunities based on my current spending patterns and balances. "
        "Suggest specific actionable changes."
    ),
    "anomaly": (
        "Identify any unusual or unexpected patterns in my recent financial data — "
        "spending spikes, balance changes, or anything that deviates from normal patterns."
    ),
}

INSIGHT_TYPES = list(_INSIGHT_PROMPTS.keys())


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def _build_financial_context(session: Session) -> dict:
    """Assemble de-identified financial data for the Claude prompt."""
    today = date.today()
    cutoff = today - timedelta(days=30)

    accounts = session.query(AccountRow).filter_by(is_active=True).all()

    balances_list: list[dict] = []
    latest_balance_by_account: dict[uuid.UUID, BalanceRow] = {}

    for acct in accounts:
        latest = (
            session.query(BalanceRow)
            .filter_by(account_id=acct.id)
            .order_by(desc(BalanceRow.balance_date))
            .first()
        )
        if latest is not None:
            latest_balance_by_account[acct.id] = latest
            balances_list.append({
                "alias": acct.alias,
                "account_type": acct.account_type,
                "balance_amount": float(latest.balance_amount),
                "balance_date": str(latest.balance_date),
            })

    # Transactions last 30 days (no merchant_name — PII risk)
    account_alias_by_id = {a.id: a.alias for a in accounts}

    raw_txns = (
        session.query(TransactionRow)
        .filter(
            TransactionRow.is_pending == False,
            TransactionRow.date >= cutoff,
        )
        .order_by(desc(TransactionRow.date))
        .limit(100)
        .all()
    )

    transactions_30d = [
        {
            "date": str(t.date),
            "amount": float(t.amount),
            "category": t.category,
            "subcategory": t.subcategory,
            "account_alias": account_alias_by_id.get(t.account_id, "Unknown"),
            "is_fixed_expense": t.is_fixed_expense,
        }
        for t in raw_txns
    ]

    # Active goals with latest snapshot
    active_goals = session.query(GoalRow).filter_by(status="active").all()
    goals_list: list[dict] = []

    for goal in active_goals:
        snapshot = (
            session.query(GoalSnapshotRow)
            .filter_by(goal_id=goal.id)
            .order_by(desc(GoalSnapshotRow.snapshot_date))
            .first()
        )
        if snapshot is not None:
            pct = float(snapshot.pct_complete)
            progress_status = "On Track" if pct >= 90 else ("At Risk" if pct >= 70 else "Off Track")
        else:
            pct = None
            progress_status = "No Data"

        goals_list.append({
            "name": goal.name,
            "goal_type": goal.goal_type,
            "target_value": float(goal.target_value),
            "target_date": str(goal.target_date) if goal.target_date else None,
            "direction": goal.direction,
            "status": goal.status,
            "pct_complete": pct,
            "progress_status": progress_status,
        })

    # Summary figures
    net_worth = Decimal("0")
    savings_balance = Decimal("0")
    liquid_cash = Decimal("0")
    cc_balance_owed = Decimal("0")

    for acct in accounts:
        bal_row = latest_balance_by_account.get(acct.id)
        if bal_row is None:
            continue
        amount = bal_row.balance_amount

        if acct.account_type == "credit_card":
            owed = abs(amount)
            cc_balance_owed += owed
            net_worth -= owed
        else:
            net_worth += amount

        if acct.account_type == "brokerage" and "schwab" in acct.institution.lower():
            savings_balance += amount
        if acct.account_type == "checking" and (
            "wells" in acct.institution.lower() or "wf" in acct.alias.lower()
        ):
            liquid_cash += amount

    return {
        "balances": balances_list,
        "transactions_30d": transactions_30d,
        "goals": goals_list,
        "summary": {
            "net_worth": float(net_worth),
            "savings_balance": float(savings_balance),
            "liquid_cash": float(liquid_cash),
            "cc_balance_owed": float(cc_balance_owed),
        },
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(context: dict) -> str:
    s = context["summary"]

    def fmt(v: float) -> str:
        return f"${v:,.2f}"

    summary_block = (
        f"- Net Worth: {fmt(s['net_worth'])}\n"
        f"- Savings Balance (Schwab Brokerage): {fmt(s['savings_balance'])}\n"
        f"- Liquid Cash (WF Checking): {fmt(s['liquid_cash'])}\n"
        f"- Outstanding CC Balance: {fmt(s['cc_balance_owed'])}"
    )

    balance_lines = "\n".join(
        f"  - {b['alias']} ({b['account_type']}): {fmt(b['balance_amount'])} as of {b['balance_date']}"
        for b in context["balances"]
    ) or "  (no balance data)"

    # Aggregate transactions by category
    category_totals: dict[str, float] = {}
    for txn in context["transactions_30d"]:
        cat = txn["category"] or "Uncategorized"
        category_totals[cat] = category_totals.get(cat, 0.0) + txn["amount"]

    if category_totals:
        sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        txn_lines = "\n".join(f"  - {cat}: {fmt(total)}" for cat, total in sorted_cats)
    else:
        txn_lines = "  (no transactions in last 30 days)"

    if context["goals"]:
        goal_lines = "\n".join(
            "  - {name}: {pct}% complete — {progress}".format(
                name=g["name"],
                pct=f"{g['pct_complete']:.1f}" if g["pct_complete"] is not None else "N/A",
                progress=g["progress_status"],
            )
            for g in context["goals"]
        )
    else:
        goal_lines = "  (no active goals)"

    return (
        "You are FinForge, Nathan's personal finance AI assistant. You have access to his "
        "current financial data (de-identified). Generate a concise, specific, actionable insight.\n\n"
        f"Current Financial Snapshot:\n{summary_block}\n\n"
        f"Account Balances:\n{balance_lines}\n\n"
        f"Recent Spending (last 30 days by category):\n{txn_lines}\n\n"
        f"Active Goals:\n{goal_lines}\n\n"
        "Respond with a single insight paragraph (2-4 sentences). "
        "Be specific with numbers. Do not use generic financial advice."
    )


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def _generate_insight(
    client: anthropic.Anthropic,
    system: str,
    insight_type: str,
) -> Optional[str]:
    user_prompt = _INSIGHT_PROMPTS.get(insight_type)
    if not user_prompt:
        logger.warning("Unknown insight_type=%s — skipping", insight_type)
        return None
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text
    except Exception as exc:
        logger.error("Claude API call failed for %s: %s", insight_type, exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_generate_claude_insights() -> None:
    """Generate all four Claude insight types and persist them."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude insight generation.")
        return

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with get_session() as session:
        context = _build_financial_context(session)
        system_prompt = _build_system_prompt(context)

        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(hours=48)

        for insight_type in INSIGHT_TYPES:
            logger.info("Generating insight: %s", insight_type)
            content = _generate_insight(client, system_prompt, insight_type)

            if content is not None:
                session.add(ClaudeInsightRow(
                    id=uuid.uuid4(),
                    insight_date=now.date(),
                    insight_type=insight_type,
                    content=content,
                    expires_at=expires_at,
                ))
                logger.info("Persisted insight %s (%d chars)", insight_type, len(content))
            else:
                logger.warning("No content for %s — skipping.", insight_type)
