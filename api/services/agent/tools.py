"""Tool surface for the FinForge financial agent (finforge-28, Phase 1).

Each tool is a typed, read-only capability the agent can call in its loop. Handlers
reuse the existing service functions and route handlers so the agent sees exactly
what the dashboard does — no duplicated business logic. All handlers take the
request-scoped SQLAlchemy `db` session plus validated kwargs and return a plain
JSON-serializable structure.

Read-only by design. Write/action tools (recategorize, dismiss finding, set
budget, trigger sync) are Phase 3 and must be confirmation-gated before landing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from models.db_models import (
    Account,
    Balance,
    ChargeGuardianFinding,
    Goal,
    GoalSnapshot,
    Holding,
    PortfolioAnalysis,
    Transaction,
)

logger = logging.getLogger("finforge.api.agent.tools")

MONEY_MARKET_TICKERS = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
_MAX_TXN_LIMIT = 200


# ---------------------------------------------------------------------------
# JSON serialization for tool results
# ---------------------------------------------------------------------------

def _default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"not JSON-serializable: {type(obj)}")


def _jsonable(value: Any) -> Any:
    """Coerce Pydantic models / dataclasses / ORM-ish values into JSON-safe data."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _t_financial_overview(db: Session) -> dict:
    """Net worth, per-account balances, liquid cash, and credit-card debt."""
    accounts = db.query(Account).filter_by(is_active=True).all()
    net_worth = Decimal("0")
    liquid_cash = Decimal("0")
    invested = Decimal("0")
    cc_owed = Decimal("0")
    balances: list[dict] = []

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
        balances.append({
            "account": acct.alias,
            "type": acct.account_type,
            "institution": acct.institution,
            "balance": float(amt),
            "as_of": latest.balance_date.isoformat(),
        })
        if acct.account_type == "credit_card":
            cc_owed += abs(amt)
            net_worth -= abs(amt)
        else:
            net_worth += amt
        if acct.account_type == "checking":
            liquid_cash += amt
        if acct.account_type in ("brokerage", "ira"):
            invested += amt

    return {
        "net_worth": float(net_worth),
        "liquid_cash": float(liquid_cash),
        "invested_assets": float(invested),
        "credit_card_owed": float(cc_owed),
        "accounts": balances,
    }


def _t_search_transactions(
    db: Session,
    start_date: str | None = None,
    end_date: str | None = None,
    merchant_contains: str | None = None,
    category: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    limit: int = 50,
) -> dict:
    """Filtered transaction search (most-recent first). Amounts are positive for
    debits/spend, negative for credits/income."""
    q = db.query(Transaction, Account.alias).join(Account, Transaction.account_id == Account.id)
    q = q.filter(Transaction.is_pending.is_(False))
    if start_date:
        q = q.filter(Transaction.date >= date.fromisoformat(start_date))
    if end_date:
        q = q.filter(Transaction.date <= date.fromisoformat(end_date))
    if merchant_contains:
        q = q.filter(Transaction.merchant_name.ilike(f"%{merchant_contains}%"))
    if category:
        q = q.filter(Transaction.category == category)
    if min_amount is not None:
        q = q.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        q = q.filter(Transaction.amount <= max_amount)

    limit = max(1, min(int(limit), _MAX_TXN_LIMIT))
    rows = q.order_by(desc(Transaction.date)).limit(limit).all()
    return {
        "count": len(rows),
        "limit": limit,
        "transactions": [
            {
                "date": t.date.isoformat(),
                "merchant": t.merchant_name,
                "category": t.category,
                "amount": float(t.amount),
                "account": alias,
            }
            for t, alias in rows
        ],
    }


def _t_spending_by_category(db: Session, days: int = 30) -> dict:
    """Total spend (debits) grouped by category over the trailing `days`."""
    days = max(1, min(int(days), 365))
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.is_pending.is_(False),
            Transaction.date >= cutoff,
            Transaction.amount > 0,
            Transaction.category != "Investment Transfer",
        )
        .all()
    )
    totals: dict[str, float] = {}
    total = 0.0
    for t in rows:
        cat = t.category or "Uncategorized"
        amt = float(t.amount)
        totals[cat] = totals.get(cat, 0.0) + amt
        total += amt
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "window_days": days,
        "total_spent": round(total, 2),
        "transaction_count": len(rows),
        "by_category": [{"category": c, "total": round(v, 2)} for c, v in ordered],
    }


def _t_get_holdings(db: Session) -> dict:
    """Latest holdings snapshot per brokerage/IRA account with value, cost basis,
    unrealized P&L, and portfolio weight."""
    accounts = db.query(Account).filter_by(is_active=True).all()
    result: list[dict] = []
    for acct in accounts:
        if acct.account_type not in ("brokerage", "ira"):
            continue
        latest_date = (
            db.query(func.max(Holding.snapshot_date)).filter_by(account_id=acct.id).scalar()
        )
        if not latest_date:
            continue
        holdings = (
            db.query(Holding)
            .filter_by(account_id=acct.id, snapshot_date=latest_date)
            .order_by(Holding.market_value.desc())
            .all()
        )
        total = sum(float(h.market_value) for h in holdings) or 0.0
        result.append({
            "account": acct.alias,
            "snapshot_date": latest_date.isoformat(),
            "total_value": round(total, 2),
            "positions": [
                {
                    "symbol": h.symbol,
                    "is_money_market": h.symbol in MONEY_MARKET_TICKERS,
                    "quantity": float(h.quantity),
                    "market_value": round(float(h.market_value), 2),
                    "cost_basis": round(float(h.cost_basis), 2) if h.cost_basis else None,
                    "unrealized_pnl": (
                        round(float(h.market_value) - float(h.cost_basis), 2)
                        if h.cost_basis else None
                    ),
                    "weight_pct": round(float(h.market_value) / total * 100, 2) if total else 0.0,
                }
                for h in holdings
            ],
        })
    return {"accounts": result}


def _t_cashflow_runway(db: Session, days: int = 60) -> dict:
    """Project the checking balance forward, with floor-crossing warnings."""
    from routers.cashflow import get_runway
    days = max(14, min(int(days), 180))
    return _jsonable(get_runway(days=days, db=db, _=None))


def _t_financial_health(db: Session) -> dict:
    """Composite 0-100 financial-health score with per-component breakdown and the
    single component that would most improve the score (top lever)."""
    from services.financial_health import compute_health_score
    return compute_health_score(db, date.today())


def _t_fire_projection(db: Session) -> dict:
    """Years-to-FI, FI number, coast-FIRE status, savings rate, expected return."""
    from fastapi import HTTPException
    from routers.fire import get_summary
    try:
        return _jsonable(get_summary(db=db, _={}))
    except HTTPException as exc:
        return {"error": str(exc.detail)}


def _t_tax_summary(db: Session, marginal_rate: float = 0.32) -> dict:
    """Realized gains YTD, tax-loss-harvesting candidates, estimated tax exposure."""
    from routers.tax import get_tax_summary
    return _jsonable(get_tax_summary(marginal_rate=marginal_rate, db=db, _={}))


def _t_dividend_income(db: Session) -> dict:
    """Projected forward annual dividend income per holding + portfolio total."""
    from routers.dividends import get_dividend_income
    return _jsonable(get_dividend_income(db=db, _=None))


def _t_charge_guardian_findings(db: Session, status: str = "open", limit: int = 20) -> dict:
    """Recent Charge Guardian findings (duplicate charges, new subscriptions,
    trial conversions, gray-charge creep). status: open | dismissed | legit | all."""
    limit = max(1, min(int(limit), 100))
    q = db.query(ChargeGuardianFinding)
    if status and status != "all":
        q = q.filter(ChargeGuardianFinding.status == status)
    rows = q.order_by(desc(ChargeGuardianFinding.created_at)).limit(limit).all()
    return {
        "count": len(rows),
        "findings": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "merchant": r.merchant,
                "title": r.title,
                "detail": r.detail,
                "amount": float(r.amount) if r.amount is not None else None,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _t_portfolio_analysis(db: Session) -> dict:
    """Latest per-symbol risk metrics (vol, beta, drawdown, TLH flags, drift) plus
    portfolio-level concentration (HHI, top-5, weighted vol, max drawdown)."""
    accounts = db.query(Account).filter_by(is_active=True).all()
    acct = next(
        (a for a in accounts if a.account_type == "brokerage" and "schwab" in a.institution.lower()),
        None,
    )
    if acct is None:
        return {"error": "no brokerage account found"}
    latest = (
        db.query(func.max(PortfolioAnalysis.analysis_date))
        .filter(PortfolioAnalysis.account_id == acct.id)
        .scalar()
    )
    if not latest:
        return {"error": "no portfolio analysis available — run the analysis cron"}
    rows = (
        db.query(PortfolioAnalysis)
        .filter(PortfolioAnalysis.account_id == acct.id, PortfolioAnalysis.analysis_date == latest)
        .all()
    )
    portfolio: dict = {}
    symbols: list[dict] = []
    for r in rows:
        if r.symbol == "__PORTFOLIO__":
            portfolio = {
                "hhi": float(r.hhi) if r.hhi is not None else None,
                "top5_concentration_pct": float(r.top5_concentration) if r.top5_concentration is not None else None,
                "weighted_volatility_pct": float(r.weighted_volatility) * 100 if r.weighted_volatility is not None else None,
                "max_drawdown_pct": float(r.max_drawdown) * 100 if r.max_drawdown is not None else None,
            }
            continue
        symbols.append({
            "symbol": r.symbol,
            "annualized_vol_pct": float(r.annualized_vol) * 100 if r.annualized_vol is not None else None,
            "beta": float(r.beta) if r.beta is not None else None,
            "drawdown_from_high_pct": float(r.drawdown_from_high) * 100 if r.drawdown_from_high is not None else None,
            "unrealized_pnl": float(r.unrealized_gl) if r.unrealized_gl is not None else None,
            "drift_pct": float(r.drift_pct) if r.drift_pct is not None else None,
            "tlh_candidate": bool(r.tlh_candidate),
            "wash_sale_risk": bool(r.wash_sale_risk),
        })
    return {"analysis_date": latest.isoformat(), "portfolio": portfolio, "symbols": symbols}


def _t_get_goals(db: Session) -> dict:
    """Active financial goals with latest progress."""
    goals = db.query(Goal).filter_by(status="active").all()
    out: list[dict] = []
    for g in goals:
        snap = (
            db.query(GoalSnapshot)
            .filter_by(goal_id=g.id)
            .order_by(desc(GoalSnapshot.snapshot_date))
            .first()
        )
        pct = float(snap.pct_complete) if snap else None
        out.append({
            "name": g.name,
            "goal_type": g.goal_type,
            "target_value": float(g.target_value) if g.target_value is not None else None,
            "pct_complete": pct,
            "status": (
                None if pct is None else
                "on_track" if pct >= 90 else "at_risk" if pct >= 70 else "off_track"
            ),
        })
    return {"goals": out}


# ---------------------------------------------------------------------------
# Registry: JSON schema (for Claude) + handler
# ---------------------------------------------------------------------------

class _Tool:
    def __init__(self, name: str, description: str, properties: dict, required: list[str],
                 handler: Callable[..., Any]):
        self.name = name
        self.description = description
        self.properties = properties
        self.required = required
        self.handler = handler

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
            },
        }


_DATE = {"type": "string", "description": "ISO date YYYY-MM-DD"}

_TOOLS: list[_Tool] = [
    _Tool("get_financial_overview",
          "Net worth, per-account balances, liquid cash, invested assets, and credit-card debt. "
          "Start here for 'how am I doing' / net-worth questions.",
          {}, [], _t_financial_overview),
    _Tool("search_transactions",
          "Search individual transactions with optional filters. Amounts: positive=spend/debit, "
          "negative=income/credit. Use this to answer 'how much did I spend at X', 'find my Y charges', "
          "or to inspect specific activity. Returns most-recent first.",
          {
              "start_date": _DATE,
              "end_date": _DATE,
              "merchant_contains": {"type": "string", "description": "case-insensitive substring of merchant name"},
              "category": {"type": "string", "description": "exact category match"},
              "min_amount": {"type": "number"},
              "max_amount": {"type": "number"},
              "limit": {"type": "integer", "description": "max rows (default 50, cap 200)"},
          }, [], _t_search_transactions),
    _Tool("spending_by_category",
          "Total spend grouped by category over a trailing window (default 30 days). "
          "Use for 'where is my money going' / category breakdowns.",
          {"days": {"type": "integer", "description": "trailing window in days (default 30, cap 365)"}},
          [], _t_spending_by_category),
    _Tool("get_holdings",
          "Current investment holdings per brokerage/IRA account: quantity, market value, cost basis, "
          "unrealized P&L, and portfolio weight.",
          {}, [], _t_get_holdings),
    _Tool("get_cashflow_runway",
          "Project the checking-account balance forward N days using recurring bills, detected income, "
          "and a discretionary-spend band. Reports if/when it crosses the configured floor. Use for "
          "'will I run low on cash' / runway questions.",
          {"days": {"type": "integer", "description": "projection horizon (default 60, 14-180)"}},
          [], _t_cashflow_runway),
    _Tool("get_financial_health",
          "Composite 0-100 financial-health score with per-component breakdown (savings rate, emergency "
          "fund, expense volatility, allocation drift) and the top lever to improve it.",
          {}, [], _t_financial_health),
    _Tool("get_fire_projection",
          "Financial-independence / retirement projection: years-to-FI, FI number, coast-FIRE status, "
          "savings rate, and expected return. Use for retirement / FIRE questions.",
          {}, [], _t_fire_projection),
    _Tool("get_tax_summary",
          "Tax picture: realized gains YTD, tax-loss-harvesting candidates, and estimated tax exposure.",
          {"marginal_rate": {"type": "number", "description": "combined marginal rate 0-1 (default 0.32)"}},
          [], _t_tax_summary),
    _Tool("get_dividend_income",
          "Projected forward annual dividend income per holding and the portfolio total.",
          {}, [], _t_dividend_income),
    _Tool("get_charge_guardian_findings",
          "Recent Charge Guardian findings: duplicate charges, new subscriptions, trial-to-paid "
          "conversions, and gray-charge creep. Use for 'anything weird on my card' questions.",
          {
              "status": {"type": "string", "description": "open | dismissed | legit | all (default open)"},
              "limit": {"type": "integer", "description": "max findings (default 20, cap 100)"},
          }, [], _t_charge_guardian_findings),
    _Tool("get_portfolio_analysis",
          "Latest portfolio risk analysis: per-symbol volatility, beta, drawdown, TLH flags, drift, plus "
          "portfolio-level concentration (HHI, top-5, weighted vol, max drawdown).",
          {}, [], _t_portfolio_analysis),
    _Tool("get_goals",
          "Active financial goals with latest progress and on-track/at-risk/off-track status.",
          {}, [], _t_get_goals),
]

_REGISTRY: dict[str, _Tool] = {t.name: t for t in _TOOLS}


def tool_schemas() -> list[dict]:
    """Anthropic tool definitions, deterministically ordered for prompt caching."""
    return [t.schema() for t in _TOOLS]


def dispatch(name: str, args: dict, db: Session) -> str:
    """Execute a tool by name and return a JSON string for the tool_result block.

    Never raises: tool errors are returned as an {"error": ...} JSON payload so the
    agent can read the failure and adapt instead of the whole turn crashing.
    """
    tool = _REGISTRY.get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        result = tool.handler(db, **(args or {}))
        return json.dumps(_jsonable(result), default=_default)
    except Exception as exc:  # noqa: BLE001 — surface any failure to the model, don't crash the turn
        logger.warning("tool %s failed: %s", name, exc, exc_info=True)
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
