"""NateBot iMessage integration — pre-formatted text endpoints for iMessage delivery."""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import verify_api_key
from models.db_models import (
    Account,
    Balance,
    ClaudeInsight,
    DrawdownPrediction,
    Goal,
    GoalAlert,
    GoalSnapshot,
    Holding,
    MarketDataCache,
    NatebotQueue,
    PortfolioAnalysis,
    Transaction,
    Watchlist,
)

logger = logging.getLogger("finforge.natebot_imessage")

router = APIRouter(prefix="/natebot", tags=["natebot-imessage"])

MONEY_MARKET = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
PORTFOLIO_SENTINEL = "__PORTFOLIO__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_balance(db: Session, alias: str) -> Decimal:
    acct = db.query(Account).filter_by(alias=alias).first()
    if not acct:
        return Decimal("0")
    bal = db.query(Balance).filter_by(account_id=acct.id).order_by(desc(Balance.balance_date)).first()
    return bal.balance_amount if bal else Decimal("0")


def _fmt(v) -> str:
    return f"${float(v):,.2f}"


def _goal_emoji(status: str) -> str:
    if status == "Completed":
        return "✅"
    if status == "On Track":
        return "🟢"
    if status == "At Risk":
        return "⚠️"
    return "🔴"


def _progress_status(goal: Goal, snap: Optional[GoalSnapshot]) -> str:
    if goal.status == "completed":
        return "Completed"
    if not snap:
        return "No Data"
    pct = float(snap.pct_complete)
    if pct >= 100:
        return "Completed"
    if pct >= 90:
        return "On Track"
    if pct >= 70:
        return "At Risk"
    return "Off Track"


# ---------------------------------------------------------------------------
# GET /natebot/pending — poll for queued notifications
# ---------------------------------------------------------------------------

@router.get("/pending")
def get_pending(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Return undelivered notifications and mark them as delivered."""
    rows = (
        db.query(NatebotQueue)
        .filter(NatebotQueue.delivered.is_(False))
        .order_by(NatebotQueue.created_at)
        .limit(20)
        .all()
    )

    messages = []
    now = datetime.now(timezone.utc)
    for r in rows:
        messages.append({
            "id": str(r.id),
            "priority": r.priority,
            "category": r.category,
            "text": r.text,
            "created_at": r.created_at.isoformat(),
        })
        r.delivered = True
        r.delivered_at = now

    db.commit()
    return {"messages": messages, "count": len(messages)}


# ---------------------------------------------------------------------------
# GET /natebot/briefing — full financial briefing as iMessage text
# ---------------------------------------------------------------------------

@router.get("/imessage/briefing")
def get_imessage_briefing(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    """Pre-formatted financial briefing for iMessage delivery."""
    today = date.today()
    day_name = today.strftime("%A, %b %d")

    # Balances
    schwab_brokerage = _latest_balance(db, "Schwab Brokerage")
    schwab_roth = _latest_balance(db, "Schwab Roth IRA")
    wf_checking = _latest_balance(db, "WF Checking")
    wf_cc = _latest_balance(db, "WF Credit Card")
    amex = _latest_balance(db, "Amex Credit Card")
    net_worth = wf_checking + schwab_brokerage + schwab_roth - wf_cc - amex

    lines = [f"💰 FinForge — {day_name}", ""]
    lines.append(f"Net Worth: {_fmt(net_worth)}")
    if schwab_brokerage:
        lines.append(f"Brokerage: {_fmt(schwab_brokerage)}")
    if schwab_roth:
        lines.append(f"Roth IRA: {_fmt(schwab_roth)}")
    if wf_checking:
        lines.append(f"Liquid Cash: {_fmt(wf_checking)}")
    cc_total = wf_cc + amex
    if cc_total:
        lines.append(f"CC Owed: {_fmt(cc_total)}")

    # Portfolio analysis summary
    brokerage = db.query(Account).filter_by(alias="Schwab Brokerage", is_active=True).first()
    if brokerage:
        pa_date = db.query(func.max(PortfolioAnalysis.analysis_date)).filter(
            PortfolioAnalysis.account_id == brokerage.id
        ).scalar()
        if pa_date:
            sentinel = db.query(PortfolioAnalysis).filter_by(
                account_id=brokerage.id, analysis_date=pa_date, symbol=PORTFOLIO_SENTINEL
            ).first()
            if sentinel and sentinel.hhi:
                lines.append("")
                lines.append(f"📊 Portfolio Risk")
                lines.append(f"HHI: {float(sentinel.hhi):.0f} | Vol: {float(sentinel.weighted_volatility or 0)*100:.1f}%")

    # Goals
    goals = db.query(Goal).filter(Goal.status == "active").all()
    if goals:
        lines.append("")
        lines.append("🎯 Goals")
        for g in goals:
            snap = db.query(GoalSnapshot).filter_by(goal_id=g.id).order_by(desc(GoalSnapshot.snapshot_date)).first()
            status = _progress_status(g, snap)
            emoji = _goal_emoji(status)
            pct = f"{float(snap.pct_complete):.1f}%" if snap else "—"
            lines.append(f"{emoji} {g.name} — {pct} ({status})")

    # Unacknowledged alerts
    alert_count = db.query(GoalAlert).filter(GoalAlert.is_acknowledged.is_(False)).count()
    if alert_count > 0:
        lines.append(f"\n🔔 {alert_count} unacknowledged alert(s)")

    # Latest insight
    now = datetime.now(timezone.utc)
    insight = db.query(ClaudeInsight).filter(ClaudeInsight.expires_at > now).order_by(
        desc(ClaudeInsight.created_at)
    ).first()
    if insight:
        lines.append(f"\n💡 {insight.content[:200]}")

    return {"text": "\n".join(lines), "generated_at": now.isoformat()}


# ---------------------------------------------------------------------------
# GET /natebot/imessage/portfolio — portfolio snapshot
# ---------------------------------------------------------------------------

@router.get("/imessage/portfolio")
def get_imessage_portfolio(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    brokerage = db.query(Account).filter_by(alias="Schwab Brokerage", is_active=True).first()
    if not brokerage:
        return {"text": "📊 No brokerage account found.", "generated_at": datetime.now(timezone.utc).isoformat()}

    pa_date = db.query(func.max(PortfolioAnalysis.analysis_date)).filter(
        PortfolioAnalysis.account_id == brokerage.id
    ).scalar()

    if not pa_date:
        # Fallback to holdings
        latest = db.query(func.max(Holding.snapshot_date)).filter(Holding.account_id == brokerage.id).scalar()
        if not latest:
            return {"text": "📊 No portfolio data yet.", "generated_at": datetime.now(timezone.utc).isoformat()}
        holdings = db.query(Holding).filter_by(account_id=brokerage.id, snapshot_date=latest).order_by(
            desc(Holding.market_value)
        ).all()
        total = sum(float(h.market_value) for h in holdings)
        lines = [f"📊 Portfolio — {_fmt(total)}", ""]
        for h in holdings:
            pct = float(h.market_value) / total * 100 if total else 0
            lines.append(f"{h.symbol} {_fmt(h.market_value)} ({pct:.1f}%)")
        return {"text": "\n".join(lines), "generated_at": datetime.now(timezone.utc).isoformat()}

    rows = db.query(PortfolioAnalysis).filter(
        PortfolioAnalysis.account_id == brokerage.id,
        PortfolioAnalysis.analysis_date == pa_date,
        PortfolioAnalysis.symbol != PORTFOLIO_SENTINEL,
    ).order_by(desc(PortfolioAnalysis.market_value)).all()

    sentinel = db.query(PortfolioAnalysis).filter_by(
        account_id=brokerage.id, analysis_date=pa_date, symbol=PORTFOLIO_SENTINEL
    ).first()

    total = sum(float(r.market_value or 0) for r in rows)
    lines = [f"📊 Portfolio — {_fmt(total)}", ""]

    for r in rows:
        parts = [f"{r.symbol} {_fmt(r.market_value)} ({float(r.pct_of_portfolio or 0):.1f}%)"]
        if r.annualized_vol is not None:
            parts.append(f"vol {float(r.annualized_vol)*100:.0f}%")
        if r.beta is not None:
            parts.append(f"β{float(r.beta):.2f}")
        if r.tlh_candidate:
            parts.append("⚠️TLH")
        lines.append(" — ".join(parts))

    if sentinel:
        lines.append("")
        lines.append(f"HHI: {float(sentinel.hhi or 0):.0f} | WeightedVol: {float(sentinel.weighted_volatility or 0)*100:.1f}%")

    return {"text": "\n".join(lines), "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# GET /natebot/imessage/predict/{symbol} — drawdown prediction
# ---------------------------------------------------------------------------

@router.get("/imessage/predict/{symbol}")
async def get_imessage_predict(
    symbol: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    symbol = symbol.upper().strip()

    from services.drawdown_features import load_model, compute_features
    import numpy as np

    model, meta = load_model()
    if model is None:
        return {"text": "🔮 Model not trained yet. Run training from Settings.", "generated_at": datetime.now(timezone.utc).isoformat()}

    try:
        from services.schwab import schwab_api_get

        data = await schwab_api_get(
            "/pricehistory",
            params={"symbol": symbol, "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1},
            market_data=True,
        )
        candles = data.get("candles", [])
        if len(candles) < 60:
            return {"text": f"🔮 Insufficient price data for {symbol}.", "generated_at": datetime.now(timezone.utc).isoformat()}

        closes = np.array([c["close"] for c in candles], dtype=float)
        volumes = np.array([c.get("volume", 0) for c in candles], dtype=float)

        quote_data = await schwab_api_get("/quotes", params={"symbols": symbol, "fields": "quote,fundamental"}, market_data=True)
        qi = quote_data.get(symbol, {})
        q = qi.get("quote", {})
        f = qi.get("fundamental", {})

        features = compute_features(closes, volumes, q.get("52WkHigh"), f.get("peRatio"), f.get("divYield"))
        if len(features) == 0:
            return {"text": f"🔮 Could not compute features for {symbol}.", "generated_at": datetime.now(timezone.utc).isoformat()}

        latest = np.nan_to_num(features[-1:], nan=0.0)
        prob = float(model.predict_proba(latest)[0, 1])

        level = "LOW" if prob < 0.2 else "MODERATE" if prob < 0.4 else "HIGH" if prob < 0.6 else "VERY HIGH"
        emoji = "🟢" if prob < 0.2 else "🟡" if prob < 0.4 else "🟠" if prob < 0.6 else "🔴"

        # Cache
        today = date.today()
        existing = db.query(DrawdownPrediction).filter_by(symbol=symbol, prediction_date=today).first()
        if existing:
            existing.drawdown_probability = round(prob, 4)
            existing.model_version = meta.get("trained_at", "unknown")
        else:
            db.add(DrawdownPrediction(
                id=uuid.uuid4(), symbol=symbol, prediction_date=today,
                drawdown_probability=round(prob, 4), model_version=meta.get("trained_at", "unknown"),
            ))
        db.commit()

        text = f"🔮 {symbol} Drawdown Risk\n\n{emoji} {prob*100:.1f}% chance of >5% drop in 30 days\nRisk Level: {level}\n\nModel AUC: {meta.get('val_auc', '—')}"
        return {"text": text, "generated_at": datetime.now(timezone.utc).isoformat()}

    except Exception as exc:
        logger.exception("Prediction failed for %s", symbol)
        return {"text": f"🔮 Prediction failed for {symbol}: {str(exc)[:100]}", "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# GET /natebot/imessage/goals — goal progress summary
# ---------------------------------------------------------------------------

@router.get("/imessage/goals")
def get_imessage_goals(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    goals = db.query(Goal).filter(Goal.status.in_(["active", "paused"])).all()

    if not goals:
        return {"text": "🎯 No active financial goals.", "generated_at": datetime.now(timezone.utc).isoformat()}

    lines = ["🎯 Financial Goals", ""]
    for g in goals:
        snap = db.query(GoalSnapshot).filter_by(goal_id=g.id).order_by(desc(GoalSnapshot.snapshot_date)).first()
        status = _progress_status(g, snap)
        emoji = _goal_emoji(status)
        if snap:
            lines.append(f"{emoji} {g.name} — {_fmt(snap.current_value)} / {_fmt(g.target_value)} ({float(snap.pct_complete):.1f}%) {status}")
        else:
            lines.append(f"{emoji} {g.name} — No Data")

    return {"text": "\n".join(lines), "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# GET /natebot/imessage/watchlist — watchlist quotes
# ---------------------------------------------------------------------------

@router.get("/imessage/watchlist")
def get_imessage_watchlist(db: Session = Depends(get_db), _: str = Depends(verify_api_key)):
    watchlists = db.query(Watchlist).all()

    if not watchlists:
        return {"text": "👁 No watchlists.", "generated_at": datetime.now(timezone.utc).isoformat()}

    lines = []
    for wl in watchlists:
        lines.append(f"👁 {wl.name}")
        symbols = [item.symbol for item in wl.items]
        if not symbols:
            lines.append("  (empty)")
            continue
        quotes = db.query(MarketDataCache).filter(MarketDataCache.symbol.in_(symbols)).all()
        qmap = {q.symbol: q for q in quotes}
        for sym in symbols:
            q = qmap.get(sym)
            if q and q.last_price is not None:
                chg = f"{float(q.net_change):+.2f}" if q.net_change is not None else ""
                pct = f", {float(q.net_change_pct):+.2f}%" if q.net_change_pct is not None else ""
                lines.append(f"  {sym} ${float(q.last_price):,.2f} ({chg}{pct})")
            else:
                lines.append(f"  {sym} — no quote")
        lines.append("")

    return {"text": "\n".join(lines).strip(), "generated_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# POST /natebot/imessage/chat — finance question via Claude
# ---------------------------------------------------------------------------

@router.post("/imessage/chat")
def post_imessage_chat(
    body: dict,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Forward a finance question to Claude with full financial context."""
    message = body.get("message", "").strip()
    if not message:
        return {"text": "Please include a question.", "generated_at": datetime.now(timezone.utc).isoformat()}

    if not settings.anthropic_api_key:
        return {"text": "Claude integration not configured.", "generated_at": datetime.now(timezone.utc).isoformat()}

    # Reuse the chat context builder
    from routers.chat import _build_chat_context
    system_prompt = _build_chat_context(db, "Nathan", user_id=None)

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system_prompt + "\n\nKeep your response under 1500 characters — it will be sent as an iMessage.",
            messages=[{"role": "user", "content": message}],
        )
        reply = response.content[0].text
        return {"text": reply, "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        return {"text": "Error processing your question. Try again later.", "generated_at": datetime.now(timezone.utc).isoformat()}
