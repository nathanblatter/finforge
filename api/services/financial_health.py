"""Financial health score — composite 0-100 score blended from four
individually-scored (0-100) components:

  1. Savings rate      — trailing-3mo (income - spend) / income
  2. Emergency fund     — liquid cash ÷ avg monthly essential spend, vs a
                           6-month target ("runway")
  3. Expense volatility — coefficient of variation (stdev / mean) of trailing
                           monthly discretionary spend, lower = better
  4. Allocation drift    — distance from target allocation (rebalancer
                           targets) if set, else drift vs trailing average mix

All formulas are intentionally simple/linear so the score is auditable and
each component can be explained to the user in the "what would help most"
drill-down (see `sensitivity()` below).

Reuses existing sign conventions from api/routers/spending.py::get_money_flow
(checking deposits are negative amounts; credit-card spend and fixed-expense
checking debits are positive amounts) rather than api/routers/kpi.py's
savings-rate query, which mixes sign conventions across account types.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.db_models import Account, Balance, PortfolioAnalysis, Transaction

# ---------------------------------------------------------------------------
# Config — weights + targets (the "formula" knobs for this feature)
# ---------------------------------------------------------------------------

COMPONENT_WEIGHTS: dict[str, float] = {
    "savings_rate": 0.30,
    "emergency_fund": 0.30,
    "expense_volatility": 0.20,
    "allocation_drift": 0.20,
}
assert abs(sum(COMPONENT_WEIGHTS.values()) - 1.0) < 1e-9

SAVINGS_RATE_LOOKBACK_MONTHS = 3
SAVINGS_RATE_FLOOR_PCT = -20.0   # score 0 at or below this savings rate
SAVINGS_RATE_TARGET_PCT = 20.0   # score 100 at or above this savings rate

EMERGENCY_FUND_TARGET_MONTHS = 6.0
EMERGENCY_FUND_LOOKBACK_MONTHS = 3  # window for avg monthly essential spend

VOLATILITY_LOOKBACK_MONTHS = 6  # trailing months of discretionary spend for CV
VOLATILITY_MIN_MONTHS = 2       # need at least this many data points

ALLOCATION_DRIFT_TARGET_MAX_PCT = 15.0  # avg abs drift >= this => score 0
ALLOCATION_DRIFT_LOOKBACK_SNAPSHOTS = 6  # fallback: trailing avg-mix window

SCORE_DROP_ALERT_THRESHOLD = 10.0  # composite points, month-over-month


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _month_bounds(anchor: date, months_back: int) -> tuple[date, date]:
    """[first_day, last_day] window covering `months_back` months ending the
    month before `anchor`'s month (i.e. trailing, excluding the partial
    current month) — anchor itself is used as the "as of" reference date."""
    end_month_first = date(anchor.year, anchor.month, 1)
    y, m = end_month_first.year, end_month_first.month
    for _ in range(months_back):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    start = date(y, m, 1)
    last_day = end_month_first - timedelta(days=1)
    return start, last_day


def _month_range(start: date, end: date) -> list[tuple[date, date]]:
    """List of (first_day, last_day) for each calendar month between start
    and end inclusive."""
    months = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        first = date(y, m, 1)
        last = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
        months.append((first, min(last, end)))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


# ---------------------------------------------------------------------------
# Raw data fetchers (reused across components)
# ---------------------------------------------------------------------------

def _flow_totals(db: Session, first_day: date, last_day: date) -> tuple[float, float, float]:
    """(income, essential_spend, discretionary_spend) for one month window,
    adapted from api/routers/spending.py::get_money_flow's sign-convention
    walk (checking deposits negative, CC/fixed-checking debits positive)."""
    rows = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= first_day,
            Transaction.date <= last_day,
            Transaction.is_pending.is_(False),
        )
        .all()
    )
    income = 0.0
    essential = 0.0
    discretionary = 0.0
    for t, a in rows:
        amt = float(t.amount)
        cat = t.category or "Other"
        if a.account_type == "checking" and amt < 0 and cat != "Investment Transfer":
            income += -amt
        elif amt > 0 and t.is_fixed_expense and cat != "Investment Transfer":
            essential += amt
        elif amt > 0 and a.account_type == "credit_card" and cat != "Investment Transfer":
            discretionary += amt
    return income, essential, discretionary


def _liquid_cash(db: Session, as_of: date | None = None) -> float:
    """WF Checking's latest balance on or before `as_of` — same "liquid cash"
    definition used by api/routers/summary.py::get_summary. Historical health
    scores previously priced every month with today's balance (finforge-35/F11)."""
    account = db.query(Account).filter_by(alias="WF Checking").first()
    if account is None:
        return 0.0
    balance = (
        db.query(Balance)
        .filter(Balance.account_id == account.id, Balance.balance_date <= (as_of or date.today()))
        .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
        .first()
    )
    return float(balance.balance_amount) if balance else 0.0


# ---------------------------------------------------------------------------
# Component 1 — Savings rate
# ---------------------------------------------------------------------------

def score_savings_rate(db: Session, as_of: date) -> dict:
    start, end = _month_bounds(as_of, SAVINGS_RATE_LOOKBACK_MONTHS)
    income = essential = discretionary = 0.0
    for first_day, last_day in _month_range(start, end):
        i, e, d = _flow_totals(db, first_day, last_day)
        income += i
        essential += e
        discretionary += d
    spend = essential + discretionary
    rate_pct = ((income - spend) / income * 100) if income > 0 else 0.0
    span = SAVINGS_RATE_TARGET_PCT - SAVINGS_RATE_FLOOR_PCT
    score = _clamp((rate_pct - SAVINGS_RATE_FLOOR_PCT) / span * 100)
    return {
        "score": round(score, 1),
        "value": round(rate_pct, 1),
        "unit": "%",
        "label": "Savings rate",
        "detail": f"{rate_pct:.1f}% saved over the trailing {SAVINGS_RATE_LOOKBACK_MONTHS} months "
                  f"(target {SAVINGS_RATE_TARGET_PCT:.0f}%+ for a perfect score).",
    }


# ---------------------------------------------------------------------------
# Component 2 — Emergency fund runway
# ---------------------------------------------------------------------------

def score_emergency_fund(db: Session, as_of: date) -> dict:
    start, end = _month_bounds(as_of, EMERGENCY_FUND_LOOKBACK_MONTHS)
    essential_total = 0.0
    for first_day, last_day in _month_range(start, end):
        _, e, _ = _flow_totals(db, first_day, last_day)
        essential_total += e
    avg_essential = essential_total / max(EMERGENCY_FUND_LOOKBACK_MONTHS, 1)
    liquid = _liquid_cash(db, as_of)
    months = (liquid / avg_essential) if avg_essential > 0 else (EMERGENCY_FUND_TARGET_MONTHS if liquid > 0 else 0.0)
    score = _clamp(months / EMERGENCY_FUND_TARGET_MONTHS * 100)
    return {
        "score": round(score, 1),
        "value": round(months, 1),
        "unit": "months",
        "label": "Emergency fund runway",
        "detail": f"${liquid:,.0f} liquid ÷ ${avg_essential:,.0f}/mo avg essential spend = "
                  f"{months:.1f} months (target {EMERGENCY_FUND_TARGET_MONTHS:.0f} months).",
    }


# ---------------------------------------------------------------------------
# Component 3 — Expense volatility
# ---------------------------------------------------------------------------

def score_expense_volatility(db: Session, as_of: date) -> dict:
    start, end = _month_bounds(as_of, VOLATILITY_LOOKBACK_MONTHS)
    monthly_discretionary = []
    for first_day, last_day in _month_range(start, end):
        _, _, d = _flow_totals(db, first_day, last_day)
        monthly_discretionary.append(d)

    if len(monthly_discretionary) < VOLATILITY_MIN_MONTHS or all(v == 0 for v in monthly_discretionary):
        return {
            "score": 50.0,
            "value": None,
            "unit": "CV",
            "label": "Expense volatility",
            "detail": "Not enough spending history yet to compute volatility — neutral score applied.",
        }

    mean = statistics.mean(monthly_discretionary)
    stdev = statistics.pstdev(monthly_discretionary)
    cv = (stdev / mean) if mean > 0 else 0.0
    score = _clamp((1 - cv) * 100)
    return {
        "score": round(score, 1),
        "value": round(cv, 3),
        "unit": "CV",
        "label": "Expense volatility",
        "detail": f"Coefficient of variation {cv:.2f} on discretionary spend over the trailing "
                  f"{len(monthly_discretionary)} months (0 = perfectly steady).",
    }


# ---------------------------------------------------------------------------
# Component 4 — Allocation drift
# ---------------------------------------------------------------------------

def score_allocation_drift(db: Session, as_of: date) -> dict:
    latest_date = (
        db.query(func.max(PortfolioAnalysis.analysis_date))
        .filter(PortfolioAnalysis.analysis_date <= as_of, PortfolioAnalysis.symbol != "__PORTFOLIO__")
        .scalar()
    )
    if latest_date is None:
        return {
            "score": 50.0,
            "value": None,
            "unit": "%",
            "label": "Allocation drift",
            "detail": "No portfolio analysis data yet — neutral score applied.",
        }

    rows = (
        db.query(PortfolioAnalysis)
        .filter(PortfolioAnalysis.analysis_date == latest_date, PortfolioAnalysis.symbol != "__PORTFOLIO__")
        .all()
    )

    targeted = [r for r in rows if r.drift_pct is not None]
    if targeted:
        weight_sum = sum(float(r.pct_of_portfolio or 0) for r in targeted) or 1.0
        avg_abs_drift = sum(abs(float(r.drift_pct)) * float(r.pct_of_portfolio or 0) for r in targeted) / weight_sum
        source = "against your configured target allocation"
    else:
        # Fallback: drift vs the trailing average mix (no targets configured).
        history_dates = (
            db.query(PortfolioAnalysis.analysis_date)
            .filter(PortfolioAnalysis.analysis_date <= as_of, PortfolioAnalysis.symbol != "__PORTFOLIO__")
            .distinct()
            .order_by(PortfolioAnalysis.analysis_date.desc())
            .limit(ALLOCATION_DRIFT_LOOKBACK_SNAPSHOTS)
            .all()
        )
        dates = [d[0] for d in history_dates]
        if len(dates) < 2:
            return {
                "score": 50.0,
                "value": None,
                "unit": "%",
                "label": "Allocation drift",
                "detail": "Not enough portfolio history yet to compute drift — neutral score applied.",
            }
        hist_rows = (
            db.query(PortfolioAnalysis)
            .filter(PortfolioAnalysis.analysis_date.in_(dates), PortfolioAnalysis.symbol != "__PORTFOLIO__")
            .all()
        )
        by_symbol: dict[str, list[float]] = {}
        for r in hist_rows:
            by_symbol.setdefault(r.symbol, []).append(float(r.pct_of_portfolio or 0))
        avg_mix = {sym: statistics.mean(vals) for sym, vals in by_symbol.items()}
        current_mix = {r.symbol: float(r.pct_of_portfolio or 0) for r in rows}
        all_syms = set(avg_mix) | set(current_mix)
        avg_abs_drift = sum(abs(current_mix.get(s, 0) - avg_mix.get(s, 0)) for s in all_syms) / 2
        source = f"against your trailing {len(dates)}-snapshot average mix (no rebalancer targets set)"

    score = _clamp(100 - avg_abs_drift * (100 / ALLOCATION_DRIFT_TARGET_MAX_PCT))
    return {
        "score": round(score, 1),
        "value": round(avg_abs_drift, 2),
        "unit": "%",
        "label": "Allocation drift",
        "detail": f"{avg_abs_drift:.1f}% average absolute drift {source} "
                  f"(target < {ALLOCATION_DRIFT_TARGET_MAX_PCT:.0f}% for a perfect score).",
    }


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

COMPONENT_SCORERS = {
    "savings_rate": score_savings_rate,
    "emergency_fund": score_emergency_fund,
    "expense_volatility": score_expense_volatility,
    "allocation_drift": score_allocation_drift,
}


def compute_health_score(db: Session, as_of: Optional[date] = None) -> dict:
    """Compute the composite 0-100 financial health score as of `as_of`
    (defaults to today), plus a transparent per-component breakdown and a
    simple sensitivity ranking of which component would move the composite
    the most if it were maxed out."""
    as_of = as_of or date.today()

    components = {name: fn(db, as_of) for name, fn in COMPONENT_SCORERS.items()}
    composite = sum(components[name]["score"] * weight for name, weight in COMPONENT_WEIGHTS.items())

    sensitivity = sorted(
        (
            {
                "component": name,
                "weight": COMPONENT_WEIGHTS[name],
                "current_score": components[name]["score"],
                "potential_gain": round((100 - components[name]["score"]) * COMPONENT_WEIGHTS[name], 1),
            }
            for name in COMPONENT_WEIGHTS
        ),
        key=lambda x: x["potential_gain"],
        reverse=True,
    )

    return {
        "as_of": as_of.isoformat(),
        "composite_score": round(composite, 1),
        "components": {
            name: {**data, "weight": COMPONENT_WEIGHTS[name]}
            for name, data in components.items()
        },
        "sensitivity": sensitivity,
        "top_lever": sensitivity[0]["component"] if sensitivity else None,
    }
