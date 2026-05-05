"""POST /api/v1/chat — Claude-powered financial chat (server-side only)."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import anthropic
from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from auth import require_auth
from config import settings
from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance, Holding, MarketDataCache, PortfolioAnalysis, Transaction, Goal, GoalSnapshot, Watchlist
from schemas.schemas import ChatRequest, ChatResponse

logger = logging.getLogger("finforge.api.chat")

router = APIRouter(tags=["chat"])

MONEY_MARKET_TICKERS = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_chat_context(db: Session, username: str, user_id: str | None = None) -> str:
    """Build a de-identified financial context string for the system prompt."""
    today = date.today()
    cutoff = today - timedelta(days=30)

    accounts = db.query(Account).filter_by(is_active=True).all()

    # Latest balance per account
    net_worth = Decimal("0")
    savings_balance = Decimal("0")
    liquid_cash = Decimal("0")
    cc_balance_owed = Decimal("0")
    balance_lines: list[str] = []

    for acct in accounts:
        latest = (
            db.query(Balance)
            .filter_by(account_id=acct.id)
            .order_by(desc(Balance.balance_date))
            .first()
        )
        if latest is None:
            continue

        amt = latest.balance_amount
        balance_lines.append(
            f"- {acct.alias} ({acct.account_type}, {acct.institution}): ${float(amt):,.2f} "
            f"(as of {latest.balance_date})"
        )

        if acct.account_type == "credit_card":
            owed = abs(amt)
            cc_balance_owed += owed
            net_worth -= owed
        else:
            net_worth += amt

        if acct.account_type == "brokerage" and "schwab" in acct.institution.lower():
            savings_balance += amt
        if acct.account_type == "checking":
            liquid_cash += amt

    # Holdings — latest snapshot per account
    holdings_lines: list[str] = []
    for acct in accounts:
        if acct.account_type not in ("brokerage", "ira"):
            continue

        latest_date = (
            db.query(func.max(Holding.snapshot_date))
            .filter_by(account_id=acct.id)
            .scalar()
        )
        if not latest_date:
            continue

        holdings = (
            db.query(Holding)
            .filter_by(account_id=acct.id, snapshot_date=latest_date)
            .order_by(Holding.market_value.desc())
            .all()
        )

        total_value = sum(float(h.market_value) for h in holdings)
        holdings_lines.append(f"\n  {acct.alias} (snapshot {latest_date}, total ${total_value:,.2f}):")
        for h in holdings:
            mv = float(h.market_value)
            cb = float(h.cost_basis) if h.cost_basis else None
            pnl = f", P&L: ${mv - cb:+,.2f}" if cb else ""
            pct = (mv / total_value * 100) if total_value else 0
            is_mm = h.symbol in MONEY_MARKET_TICKERS
            label = " (money market/cash)" if is_mm else ""
            holdings_lines.append(
                f"    - {h.symbol}{label}: {float(h.quantity):.4f} shares, "
                f"${mv:,.2f} ({pct:.1f}%){pnl}"
            )

    # Category totals from last 30 days
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.is_pending == False,
            Transaction.date >= cutoff,
        )
        .all()
    )

    category_totals: dict[str, float] = {}
    recent_txn_count = 0
    total_spent = 0.0
    for t in txns:
        cat = t.category or "Uncategorized"
        amt = float(t.amount)
        category_totals[cat] = category_totals.get(cat, 0.0) + amt
        if amt > 0:
            total_spent += amt
        recent_txn_count += 1

    if category_totals:
        sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        spend_lines = "\n".join(f"  - {cat}: ${total:,.2f}" for cat, total in sorted_cats)
    else:
        spend_lines = "  (no transactions in last 30 days)"

    # Active goals with progress
    goals = db.query(Goal).filter_by(status="active").all()
    goal_lines: list[str] = []
    for g in goals:
        snap = (
            db.query(GoalSnapshot)
            .filter_by(goal_id=g.id)
            .order_by(desc(GoalSnapshot.snapshot_date))
            .first()
        )
        if snap:
            pct = float(snap.pct_complete)
            status_label = "On Track" if pct >= 90 else ("At Risk" if pct >= 70 else "Off Track")
            goal_lines.append(
                f"  - {g.name} ({g.goal_type}): {pct:.1f}% complete — {status_label} "
                f"(target: ${float(g.target_value):,.2f})"
            )
        else:
            goal_lines.append(f"  - {g.name} ({g.goal_type}): No data yet")

    # Watchlists with cached quotes
    watchlist_lines: list[str] = []
    if user_id:
        user_watchlists = (
            db.query(Watchlist)
            .filter_by(user_id=user_id)
            .all()
        )
        for wl in user_watchlists:
            symbols = [item.symbol for item in wl.items]
            if not symbols:
                watchlist_lines.append(f"  - {wl.name}: (empty)")
                continue

            # Fetch cached quotes for these symbols
            cache_rows = (
                db.query(MarketDataCache)
                .filter(MarketDataCache.symbol.in_(symbols))
                .all()
            )
            quote_map = {r.symbol: r for r in cache_rows}

            sym_parts: list[str] = []
            for sym in symbols:
                q = quote_map.get(sym)
                if q and q.last_price is not None:
                    chg = ""
                    if q.net_change is not None and q.net_change_pct is not None:
                        chg = f", chg: {float(q.net_change):+.2f} ({float(q.net_change_pct):+.2f}%)"
                    sym_parts.append(f"{sym} ${float(q.last_price):,.2f}{chg}")
                else:
                    sym_parts.append(f"{sym} (no quote)")

            watchlist_lines.append(f"  - {wl.name}: {', '.join(sym_parts)}")

    # Portfolio analysis (latest)
    analysis_lines: list[str] = []
    pa_sentinel = None
    brokerage_acct = next((a for a in accounts if a.account_type == "brokerage" and "schwab" in a.institution.lower()), None)
    if brokerage_acct:
        from sqlalchemy import func as sqlfunc
        latest_pa_date = (
            db.query(sqlfunc.max(PortfolioAnalysis.analysis_date))
            .filter(PortfolioAnalysis.account_id == brokerage_acct.id)
            .scalar()
        )
        if latest_pa_date:
            pa_rows = (
                db.query(PortfolioAnalysis)
                .filter(PortfolioAnalysis.account_id == brokerage_acct.id, PortfolioAnalysis.analysis_date == latest_pa_date)
                .all()
            )
            for r in pa_rows:
                if r.symbol == "__PORTFOLIO__":
                    pa_sentinel = r
                    continue
                parts = [f"{r.symbol}:"]
                if r.annualized_vol is not None:
                    parts.append(f"vol={float(r.annualized_vol)*100:.1f}%")
                if r.beta is not None:
                    parts.append(f"beta={float(r.beta):.2f}")
                if r.drawdown_from_high is not None:
                    parts.append(f"dd={float(r.drawdown_from_high)*100:.1f}%")
                if r.unrealized_gl is not None:
                    parts.append(f"P&L=${float(r.unrealized_gl):+,.2f}")
                if r.tlh_candidate:
                    ws = " (WASH SALE RISK)" if r.wash_sale_risk else ""
                    parts.append(f"TLH candidate{ws}")
                if r.drift_pct is not None:
                    parts.append(f"drift={float(r.drift_pct):+.1f}%")
                analysis_lines.append("  " + " ".join(parts))

            if pa_sentinel:
                analysis_lines.insert(0,
                    f"  Portfolio: HHI={float(pa_sentinel.hhi or 0):.0f}, "
                    f"Top5={float(pa_sentinel.top5_concentration or 0):.1f}%, "
                    f"WeightedVol={float(pa_sentinel.weighted_volatility or 0)*100:.1f}%, "
                    f"MaxDD={float(pa_sentinel.max_drawdown or 0)*100:.1f}%"
                )

    fmt = lambda v: f"${float(v):,.2f}"

    return (
        f"You are FinForge, a personal finance AI assistant for {username}. "
        "Answer questions about their finances using the data below. Be specific with numbers. "
        "Keep responses concise (2-4 sentences unless a detailed breakdown is asked for). "
        "You can give investment opinions and financial advice when asked. "
        "If the data doesn't contain what's needed to answer, say so.\n\n"
        f"Today: {today}\n\n"
        f"=== FINANCIAL SNAPSHOT ===\n"
        f"Net Worth: {fmt(net_worth)}\n"
        f"Savings (Brokerage): {fmt(savings_balance)}\n"
        f"Liquid Cash: {fmt(liquid_cash)}\n"
        f"Credit Card Owed: {fmt(cc_balance_owed)}\n\n"
        f"=== ACCOUNT BALANCES ===\n"
        + "\n".join(balance_lines or ["(no accounts)"])
        + "\n\n"
        f"=== PORTFOLIO HOLDINGS ===\n"
        + "\n".join(holdings_lines or ["(no holdings data)"])
        + "\n\n"
        f"=== SPENDING (Last 30 Days) ===\n"
        f"Total transactions: {recent_txn_count}\n"
        f"Total spent: {fmt(total_spent)}\n"
        f"By category:\n{spend_lines}\n\n"
        f"=== ACTIVE GOALS ===\n"
        + "\n".join(goal_lines or ["(no active goals)"])
        + "\n\n"
        f"=== WATCHLISTS ===\n"
        + "\n".join(watchlist_lines or ["(no watchlists)"])
        + "\n\n"
        f"=== PORTFOLIO ANALYSIS ===\n"
        + "\n".join(analysis_lines or ["(no analysis data — run portfolio analysis cron job)"])
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(require_auth),
) -> ChatResponse:
    """Claude-powered financial chat. Session history in request body, not persisted."""
    if not settings.anthropic_api_key:
        return ChatResponse(reply="Claude integration is not configured. Set ANTHROPIC_API_KEY.")

    username = token_payload.get("username", "User")
    user_id = token_payload.get("sub")
    system_prompt = _build_chat_context(db, username, user_id=user_id)

    # Build messages: history + new user message
    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return ChatResponse(reply=response.content[0].text)
    except Exception as exc:
        logger.error("Claude chat API error: %s", exc, exc_info=True)
        return ChatResponse(reply="I encountered an error processing your request. Please try again.")
