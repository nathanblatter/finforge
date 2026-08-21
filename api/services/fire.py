"""
FIRE / retirement projector math for FinForge.

Reuses the wave-4 quant suite rather than reinventing it:
  - `services.quant.bootstrap_monthly_returns` — the same block-bootstrap
    engine that powers /quant/montecarlo drives both the years-to-FI
    distribution and the safe-withdrawal-rate stress test here, just pointed
    at the user's real current allocation and, for SWR, extended to subtract
    a withdrawal each month (decumulation) instead of only adding
    contributions.
  - `services.quant.aligned_returns` / `fetch_histories` — build the daily
    return matrix for whatever symbols are actually held.
  - `services.quant.TRADING_DAYS`, `MONEY_MARKET` — shared constants.

Net worth, savings rate, and allocation are computed here directly against
the ORM (Account/Balance/Holding/Transaction) rather than via the Wrapped/
summary/kpi helpers, because none of those exist as reusable functions today
(summary.py and kpi.py both hardcode a fixed 5-account list or raw SQL inline
in a router) — see the FIRE work item notes. The definitions below mirror
summary.py's net-worth semantics (checking + brokerage + ira − credit cards)
but generalize across *all* active linked accounts instead of five hardcoded
aliases, per the finforge-6 requirement to use "all linked accounts".
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.db_models import Account, Balance, Holding, Transaction
from services import quant

logger = logging.getLogger("finforge.fire")

TRADING_DAYS = quant.TRADING_DAYS
DEFAULT_WITHDRAWAL_RATE = 0.04
SWR_RATES = [0.030, 0.035, 0.040, 0.045]
SWR_HORIZONS = [30, 40, 50]


# ---------------------------------------------------------------------------
# Net worth (all linked accounts)
# ---------------------------------------------------------------------------

def _latest_balances_by_account(db: Session) -> list[tuple[Account, float]]:
    """Latest balance_amount per active account."""
    accounts = db.query(Account).filter(Account.is_active.is_(True)).all()
    out = []
    for acct in accounts:
        bal = (
            db.query(Balance)
            .filter(Balance.account_id == acct.id)
            .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
            .first()
        )
        if bal is not None:
            out.append((acct, float(bal.balance_amount)))
    return out


def compute_net_worth(db: Session) -> dict:
    """Net worth + invested-assets breakdown across every active linked account.

    Mirrors summary.py's sign convention (assets positive, credit_card
    balances subtracted) but sums whatever accounts are actually linked
    instead of five hardcoded aliases.
    """
    rows = _latest_balances_by_account(db)
    if not rows:
        raise ValueError("No balance data available")

    cash = 0.0
    invested = 0.0
    debt = 0.0
    for acct, amount in rows:
        if acct.account_type == "credit_card":
            debt += amount
        elif acct.account_type in ("brokerage", "ira"):
            invested += amount
        else:  # checking, and any future cash-like type
            cash += amount

    net_worth = cash + invested - debt
    dates = []
    for acct, _amt in rows:
        bal = (
            db.query(Balance)
            .filter(Balance.account_id == acct.id)
            .order_by(Balance.balance_date.desc())
            .first()
        )
        if bal is not None:
            dates.append(bal.balance_date)
    return {
        "net_worth": round(net_worth, 2),
        "invested_assets": round(invested, 2),
        "cash": round(cash, 2),
        "debt": round(debt, 2),
        "as_of": max(dates).isoformat() if dates else None,
    }


# ---------------------------------------------------------------------------
# Savings rate (income minus spend from transaction history)
# ---------------------------------------------------------------------------

def compute_savings_rate(db: Session, months: int = 12) -> dict:
    """Trailing-N-month income/expenses, annualized savings rate + $ savings.

    Uses the canonical debits-positive classification shared with
    services.financial_health._flow_totals (checking deposits = income;
    fixed checking debits + credit-card debits = spend; pending and
    Investment Transfer rows excluded). The previous raw-sign split
    (amount > 0 = income) was inverted under this convention and fed the
    FIRE engine an income figure as annual spend (finforge-14).
    """
    from services.financial_health import _flow_totals

    today = date.today()
    since = today - timedelta(days=round(months * 365.25 / 12))
    income, essential, discretionary = _flow_totals(db, since, today)
    expenses = essential + discretionary
    n_years = months / 12.0

    income_annualized = income / n_years if n_years > 0 else 0.0
    expenses_annualized = expenses / n_years if n_years > 0 else 0.0
    annual_savings = income_annualized - expenses_annualized
    savings_rate = (annual_savings / income_annualized) if income_annualized > 0 else 0.0

    return {
        "window_months": months,
        "income_annualized": round(income_annualized, 2),
        "expenses_annualized": round(expenses_annualized, 2),
        "annual_savings": round(annual_savings, 2),
        "savings_rate": round(savings_rate, 4),
    }


# ---------------------------------------------------------------------------
# Real current allocation (brokerage + IRA, all held symbols)
# ---------------------------------------------------------------------------

def invested_weights(db: Session) -> tuple[dict[str, float], float]:
    """{symbol: weight} over risky (non-money-market) holdings, plus total
    invested value (incl. money-market cash), across ALL brokerage + IRA
    accounts — not just the single "Schwab Brokerage" alias that
    /quant/montecarlo uses. This is the FIRE feature's real-allocation
    input, generalizing quant.py's `_held_weights`."""
    accounts = (
        db.query(Account)
        .filter(Account.is_active.is_(True), Account.account_type.in_(["brokerage", "ira"]))
        .all()
    )
    if not accounts:
        raise ValueError("No active brokerage/IRA accounts linked")

    totals: dict[str, float] = {}
    total_value = 0.0
    for acct in accounts:
        latest = db.query(func.max(Holding.snapshot_date)).filter(Holding.account_id == acct.id).scalar()
        if not latest:
            continue
        rows = db.query(Holding).filter(Holding.account_id == acct.id, Holding.snapshot_date == latest).all()
        for h in rows:
            mv = float(h.market_value)
            total_value += mv
            totals[h.symbol] = totals.get(h.symbol, 0.0) + mv

    risky = {s: v for s, v in totals.items() if s not in quant.MONEY_MARKET}
    risky_total = sum(risky.values())
    if risky_total <= 0:
        raise ValueError("No risky holdings to analyze across brokerage/IRA accounts")
    return {s: v / risky_total for s, v in risky.items()}, total_value


async def portfolio_return_series(db: Session) -> tuple[np.ndarray, list[str], dict[str, float], float]:
    """(daily portfolio returns, symbols, weights, total invested value) for
    the real cross-account allocation, reusing quant's history fetch/align."""
    weights, total_value = invested_weights(db)
    histories = await quant.fetch_histories(sorted(weights.keys()))
    returns, symbols = quant.aligned_returns(histories)
    if returns.size == 0:
        raise ValueError("Could not fetch price history for held symbols")
    w = np.array([weights.get(s, 0.0) for s in symbols])
    w_sum = w.sum()
    if w_sum <= 0:
        raise ValueError("No weights for held symbols")
    w = w / w_sum
    portfolio_returns = returns @ w
    return portfolio_returns, symbols, weights, total_value


def expected_annual_return(portfolio_returns: np.ndarray) -> float:
    """Annualized mean daily return of the real portfolio — the deterministic
    growth-rate input, same annualization convention as quant.compute_frontier."""
    if portfolio_returns.size == 0:
        return 0.0
    return float(portfolio_returns.mean() * TRADING_DAYS)


# ---------------------------------------------------------------------------
# FI number / years-to-FI (deterministic)
# ---------------------------------------------------------------------------

def fi_number(annual_spend: float, withdrawal_rate: float) -> float:
    if withdrawal_rate <= 0:
        raise ValueError("withdrawal_rate must be > 0")
    return annual_spend / withdrawal_rate


def years_to_fi_deterministic(
    current_invested: float,
    annual_contribution: float,
    expected_return: float,
    target: float,
) -> Optional[float]:
    """Closed-form years to reach `target` given a constant annual real
    contribution and annual growth rate `expected_return`. Returns None if
    the target is unreachable (contribution <= 0, return <= 0, and current
    balance is below target)."""
    if current_invested >= target:
        return 0.0
    r = expected_return
    c = annual_contribution
    if abs(r) < 1e-9:
        if c <= 0:
            return None
        return (target - current_invested) / c
    numerator = target * r + c
    denominator = current_invested * r + c
    if numerator <= 0 or denominator <= 0:
        return None
    ratio = numerator / denominator
    if ratio <= 0:
        return None
    import math
    years = math.log(ratio) / math.log(1 + r)
    return years if years > 0 else 0.0


# ---------------------------------------------------------------------------
# Coast-FIRE
# ---------------------------------------------------------------------------

def coast_fire_number(target: float, expected_return: float, years_until_retirement: float) -> float:
    """The amount that, with zero further contributions, grows to `target`
    by retirement given `expected_return`."""
    if years_until_retirement <= 0:
        return target
    return target / ((1 + expected_return) ** years_until_retirement)


def coast_age(
    current_invested: float,
    annual_contribution: float,
    expected_return: float,
    current_age: float,
    target_age: float,
    target: float,
    step_years: float = 0.25,
) -> Optional[float]:
    """The age at which continuing to contribute puts the investor ahead of
    the *shrinking* coast number for retiring at `target_age` — i.e. the age
    at which they could stop contributing entirely and still hit `target` by
    `target_age` on growth alone. Walked year-by-year (quarterly steps)
    rather than solved in closed form since the coast threshold itself moves
    with time; simple to reason about and cheap at this size."""
    if current_invested >= coast_fire_number(target, expected_return, target_age - current_age):
        return current_age

    value = current_invested
    age = current_age
    max_iters = int((target_age - current_age) / step_years) + 1
    for _ in range(max(max_iters, 0)):
        years_left = target_age - age
        if years_left <= 0:
            return None
        needed = coast_fire_number(target, expected_return, years_left)
        if value >= needed:
            return round(age, 2)
        value = value * (1 + expected_return) ** step_years + annual_contribution * step_years
        age += step_years
    return None


# ---------------------------------------------------------------------------
# Monte Carlo years-to-FI (real allocation)
# ---------------------------------------------------------------------------

def simulate_years_to_fi(
    portfolio_returns: np.ndarray,
    initial_value: float,
    annual_contribution: float,
    target_value: float,
    max_years: int = 60,
    n_sims: int = 2000,
    seed: Optional[int] = None,
) -> dict:
    """Distribution of years-to-FI via the shared block-bootstrap engine
    (services.quant.bootstrap_monthly_returns) pointed at the real portfolio
    return series, with a level monthly contribution instead of quant's
    default no-withdrawal accumulation-only path."""
    rng = np.random.default_rng(seed)
    months = max_years * 12
    monthly = quant.bootstrap_monthly_returns(portfolio_returns, n_sims, months, rng)
    monthly_contribution = annual_contribution / 12.0

    values = np.full(n_sims, initial_value, dtype=float)
    hit_month = np.full(n_sims, -1, dtype=int)
    if initial_value >= target_value:
        hit_month[:] = 0
    for m in range(months):
        still_going = hit_month < 0
        values[still_going] = values[still_going] * (1.0 + monthly[still_going, m]) + monthly_contribution
        newly_hit = still_going & (values >= target_value)
        hit_month[newly_hit] = m + 1

    never = hit_month < 0
    prob_never = float(never.mean())
    years = np.where(never, max_years, hit_month / 12.0)

    p10, p50, p90 = np.percentile(years, [10, 50, 90])
    return {
        "target_value": round(target_value, 2),
        "initial_value": round(initial_value, 2),
        "annual_contribution": round(annual_contribution, 2),
        "n_sims": n_sims,
        "max_years": max_years,
        "years_to_fi_p10": round(float(p10), 2),
        "years_to_fi_p50": round(float(p50), 2),
        "years_to_fi_p90": round(float(p90), 2),
        "prob_never_by_cap": round(prob_never, 4),
    }


# ---------------------------------------------------------------------------
# Safe-withdrawal-rate stress test (decumulation)
# ---------------------------------------------------------------------------

def _run_decumulation(
    monthly: np.ndarray,
    initial_value: float,
    annual_withdrawal_rate: float,
    with_path: bool = False,
) -> dict:
    """Apply a constant withdrawal rate against a precomputed (n_sims, months)
    bootstrap return matrix. Split out from `simulate_decumulation` so
    `swr_table` can bootstrap once per horizon and reuse the same simulated
    paths across every rate it tests (methodologically cleaner — rates are
    compared on identical scenarios — and far cheaper than re-bootstrapping
    per rate)."""
    n_sims, months = monthly.shape
    monthly_withdrawal = initial_value * annual_withdrawal_rate / 12.0

    values = np.full(n_sims, initial_value, dtype=float)
    depleted = np.zeros(n_sims, dtype=bool)
    path_percentiles = []

    for m in range(months):
        alive = ~depleted
        values[alive] = values[alive] * (1.0 + monthly[alive, m]) - monthly_withdrawal
        newly_depleted = alive & (values <= 0)
        values[newly_depleted] = 0.0
        depleted |= newly_depleted
        if with_path and (m + 1) % 12 == 0:
            p = np.percentile(values, [10, 50, 90])
            path_percentiles.append({
                "year": (m + 1) // 12,
                "p10": round(float(p[0]), 2),
                "p50": round(float(p[1]), 2),
                "p90": round(float(p[2]), 2),
            })

    success_prob = float((~depleted).mean())
    return {
        "success_probability": round(success_prob, 4),
        "worst_decile_path": path_percentiles,
    }


def simulate_decumulation(
    portfolio_returns: np.ndarray,
    initial_value: float,
    annual_withdrawal_rate: float,
    years: int,
    n_sims: int = 2000,
    seed: Optional[int] = None,
) -> dict:
    """Success probability of a constant real withdrawal rate over `years`,
    via the same block-bootstrap engine used for accumulation MC
    (services.quant.bootstrap_monthly_returns), run in reverse (withdraw
    instead of contribute).

    "Success" = balance never hits zero before the horizon ends. Also
    reports the worst-decile (10th percentile) ending-balance path so the
    UI can chart a stress scenario, not just the headline probability.
    """
    rng = np.random.default_rng(seed)
    months = years * 12
    monthly = quant.bootstrap_monthly_returns(portfolio_returns, n_sims, months, rng)
    result = _run_decumulation(monthly, initial_value, annual_withdrawal_rate, with_path=True)
    return {
        "initial_value": round(initial_value, 2),
        "annual_withdrawal_rate": annual_withdrawal_rate,
        "years": years,
        "n_sims": n_sims,
        **result,
    }


def swr_table(
    portfolio_returns: np.ndarray,
    initial_value: float,
    rates: list[float] = SWR_RATES,
    horizons: list[int] = SWR_HORIZONS,
    n_sims: int = 1500,
    seed: Optional[int] = None,
) -> dict:
    """Success probability grid across withdrawal rates x horizons, plus the
    max safe rate (nearest 0.1%) clearing 90% and 95% success at each
    horizon. Bootstraps monthly return paths once per horizon and replays
    every candidate rate against those same paths (see `_run_decumulation`),
    so the whole grid + fine max-safe-rate scan costs one bootstrap per
    horizon rather than one per (rate, horizon) pair."""
    fine_rates = [round(r, 3) for r in np.arange(0.020, 0.0601, 0.001)]
    rows = []
    max_safe = {}

    for years in horizons:
        rng = np.random.default_rng(seed)
        months = years * 12
        monthly = quant.bootstrap_monthly_returns(portfolio_returns, n_sims, months, rng)

        for rate in rates:
            prob = _run_decumulation(monthly, initial_value, rate)["success_probability"]
            rows.append({"withdrawal_rate": rate, "years": years, "success_probability": prob})

        safe_90 = 0.0
        safe_95 = 0.0
        for rate in fine_rates:
            prob = _run_decumulation(monthly, initial_value, rate)["success_probability"]
            if prob >= 0.90:
                safe_90 = rate
            if prob >= 0.95:
                safe_95 = rate
        max_safe[str(years)] = {"rate_90": round(safe_90, 3), "rate_95": round(safe_95, 3)}

    return {
        "initial_value": round(initial_value, 2),
        "table": rows,
        "max_safe_rate_by_horizon": max_safe,
    }
