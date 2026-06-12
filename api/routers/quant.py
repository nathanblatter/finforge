"""Quant endpoints — efficient frontier, correlation clusters, IV vs HV, Monte Carlo."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db
from models.db_models import Account, Holding
from services import quant

logger = logging.getLogger("finforge.quant")

router = APIRouter(prefix="/quant", tags=["quant"])


def _get_brokerage(db: Session) -> Account:
    acct = db.query(Account).filter(Account.alias == "Schwab Brokerage", Account.is_active.is_(True)).first()
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active brokerage account")
    return acct


def _held_weights(db: Session) -> tuple[dict[str, float], float]:
    """Latest-snapshot holdings as {symbol: weight} over risky (non-MM) assets,
    plus total portfolio value including money market."""
    acct = _get_brokerage(db)
    latest = db.query(func.max(Holding.snapshot_date)).filter(Holding.account_id == acct.id).scalar()
    if not latest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No holdings data")
    rows = db.query(Holding).filter(Holding.account_id == acct.id, Holding.snapshot_date == latest).all()

    total_value = sum(float(h.market_value) for h in rows)
    risky = {h.symbol: float(h.market_value) for h in rows if h.symbol not in quant.MONEY_MARKET}
    risky_total = sum(risky.values())
    if risky_total <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No risky holdings to analyze")
    return {s: v / risky_total for s, v in risky.items()}, total_value


async def _returns_for_held(db: Session) -> tuple:
    """(returns matrix, symbols, weights, total_value) for held risky symbols, cached."""
    weights, total_value = _held_weights(db)
    cache_key = "returns:" + ",".join(sorted(weights))
    cached = quant.cache_get(cache_key)
    if cached is not None:
        returns, symbols = cached
    else:
        histories = await quant.fetch_histories(sorted(weights.keys()))
        returns, symbols = quant.aligned_returns(histories)
        if returns.size == 0:
            raise HTTPException(status_code=502, detail="Could not fetch price history from Schwab")
        quant.cache_set(cache_key, (returns, symbols))
    return returns, symbols, weights, total_value


# ---------------------------------------------------------------------------
# Efficient frontier
# ---------------------------------------------------------------------------

@router.get("/frontier")
async def get_frontier(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    cached = quant.cache_get("frontier")
    if cached is not None:
        return cached
    returns, symbols, weights, _total = await _returns_for_held(db)
    if len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 holdings for frontier analysis")
    result = quant.compute_frontier(returns, symbols, weights)
    quant.cache_set("frontier", result)
    return result


# ---------------------------------------------------------------------------
# What-if rebalancer
# ---------------------------------------------------------------------------

class WhatIfRequest(BaseModel):
    weights: dict[str, float] = Field(
        ..., description="symbol → proposed weight; renormalized server-side"
    )


@router.post("/whatif")
async def run_whatif(
    body: WhatIfRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Risk/return/Sharpe for a hypothetical weighting of the held symbols —
    powers the rebalancing sliders on the frontier chart."""
    returns, symbols, weights, _total = await _returns_for_held(db)
    if len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 holdings for what-if analysis")
    try:
        return quant.compute_whatif(returns, symbols, body.weights, weights)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Correlation clusters
# ---------------------------------------------------------------------------

@router.get("/clusters")
async def get_clusters(
    threshold: float = Query(default=0.65, ge=0.3, le=0.95),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    cache_key = f"clusters:{threshold}"
    cached = quant.cache_get(cache_key)
    if cached is not None:
        return cached
    returns, symbols, weights, _total = await _returns_for_held(db)
    if len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 holdings for cluster analysis")
    result = quant.compute_clusters(returns, symbols, weights, corr_threshold=threshold)
    quant.cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# IV vs HV
# ---------------------------------------------------------------------------

@router.get("/iv-hv")
async def get_iv_hv(
    symbols: Optional[str] = Query(default=None, description="Comma-separated; defaults to held symbols"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    if symbols:
        sym_list = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()})
    else:
        weights, _total = _held_weights(db)
        sym_list = sorted(weights.keys())

    cache_key = "ivhv:" + ",".join(sym_list)
    cached = quant.cache_get(cache_key)
    if cached is not None:
        return cached

    results = []
    for sym in sym_list:
        closes = await quant.fetch_closes(sym)
        hv = quant.historical_vol_30d(closes)
        chain = await quant.fetch_options_chain(sym)
        iv = quant.extract_atm_iv(chain) if chain else None
        entry = {"symbol": sym, "hv_30d": None, "iv_30d": None, "iv_hv_ratio": None, "signal": "UNKNOWN"}
        if hv is not None:
            entry["hv_30d"] = round(hv, 4)
        if iv is not None:
            entry["iv_30d"] = round(iv, 4)
        if hv is not None and iv is not None and hv > 0:
            entry["iv_hv_ratio"] = round(iv / hv, 3)
            entry["signal"] = quant.iv_hv_signal(iv, hv)
        results.append(entry)

    result = {"results": results}
    quant.cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

class MonteCarloRequest(BaseModel):
    initial_value: Optional[float] = Field(default=None, ge=0, description="Defaults to current portfolio value")
    monthly_contribution: float = Field(default=0, ge=0)
    years: int = Field(default=10, ge=1, le=50)
    target_value: Optional[float] = Field(default=None, gt=0)
    n_sims: int = Field(default=2000, ge=500, le=5000)


@router.post("/montecarlo")
async def run_monte_carlo(
    body: MonteCarloRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    returns, symbols, weights, total_value = await _returns_for_held(db)
    w = [weights.get(s, 0.0) for s in symbols]
    w_sum = sum(w)
    if w_sum <= 0:
        raise HTTPException(status_code=400, detail="No weights for held symbols")
    import numpy as np
    w_arr = np.array(w) / w_sum
    portfolio_returns = returns @ w_arr

    initial = body.initial_value if body.initial_value is not None else total_value
    try:
        return quant.monte_carlo_projection(
            portfolio_returns,
            initial_value=initial,
            monthly_contribution=body.monthly_contribution,
            years=body.years,
            target_value=body.target_value,
            n_sims=body.n_sims,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Market regime
# ---------------------------------------------------------------------------

@router.get("/regime")
def get_regime(
    history_days: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Latest market regime classification plus recent history."""
    from models.db_models import MarketRegime

    rows = (
        db.query(MarketRegime)
        .order_by(desc(MarketRegime.regime_date))
        .limit(history_days)
        .all()
    )
    if not rows:
        return {"current": None, "history": []}

    def _row(r) -> dict:
        return {
            "date": r.regime_date.isoformat(),
            "regime": r.regime,
            "realized_vol_20d": float(r.realized_vol_20d) if r.realized_vol_20d is not None else None,
            "trend_60d": float(r.trend_60d) if r.trend_60d is not None else None,
            "sma20_vs_sma50": float(r.sma20_vs_sma50) if r.sma20_vs_sma50 is not None else None,
        }

    return {"current": _row(rows[0]), "history": [_row(r) for r in rows]}


# ---------------------------------------------------------------------------
# Covered call screener
# ---------------------------------------------------------------------------

@router.get("/covered-calls")
async def get_covered_calls(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """~30-delta call premium yield for each held position with options."""
    cached = quant.cache_get("covered_calls")
    if cached is not None:
        return cached

    acct = _get_brokerage(db)
    latest = db.query(func.max(Holding.snapshot_date)).filter(Holding.account_id == acct.id).scalar()
    if not latest:
        raise HTTPException(status_code=404, detail="No holdings data")
    holdings = (
        db.query(Holding)
        .filter(Holding.account_id == acct.id, Holding.snapshot_date == latest)
        .all()
    )

    results = []
    for h in holdings:
        if h.symbol in quant.MONEY_MARKET:
            continue
        shares = float(h.quantity)
        chain = await quant.fetch_options_chain(h.symbol)
        call = quant.best_covered_call(chain) if chain else None
        contracts = int(shares // 100)
        entry = {
            "symbol": h.symbol,
            "shares": round(shares, 4),
            "contracts_available": contracts,
            "call": call,
            "est_monthly_income": None,
            "est_annual_income": None,
        }
        if call and contracts > 0:
            per_contract = call["premium"] * 100
            cycles_per_year = 365 / call["expiration_days"]
            entry["est_monthly_income"] = round(per_contract * contracts * cycles_per_year / 12, 2)
            entry["est_annual_income"] = round(per_contract * contracts * cycles_per_year, 2)
        results.append(entry)

    # Positions with sellable contracts first, by income
    results.sort(key=lambda r: (r["est_annual_income"] or 0, r["call"] is not None), reverse=True)
    result = {"as_of": latest.isoformat(), "results": results}
    quant.cache_set("covered_calls", result)
    return result


# ---------------------------------------------------------------------------
# Portfolio vs benchmark
# ---------------------------------------------------------------------------

@router.get("/benchmark")
async def get_benchmark(
    days: int = Query(default=365, ge=30, le=365),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Time-weighted portfolio return vs SPY, from daily holdings snapshots.
    Flows are approximated by day-over-day cost basis changes."""
    cache_key = f"benchmark:{days}"
    cached = quant.cache_get(cache_key)
    if cached is not None:
        return cached

    from datetime import timedelta as _td
    from datetime import date as _date

    acct = _get_brokerage(db)
    since = _date.today() - _td(days=days)
    rows = (
        db.query(
            Holding.snapshot_date,
            func.sum(Holding.market_value),
            func.sum(func.coalesce(Holding.cost_basis, Holding.market_value)),
        )
        .filter(Holding.account_id == acct.id, Holding.snapshot_date >= since)
        .group_by(Holding.snapshot_date)
        .order_by(Holding.snapshot_date)
        .all()
    )
    snapshots = [
        {"date": d, "value": float(v), "cost_basis": float(cb)}
        for d, v, cb in rows
        if v is not None and float(v) > 0
    ]
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 daily holdings snapshots — check back after tomorrow's sync",
        )

    spy = await quant.fetch_spy_closes_by_date()
    if not spy:
        raise HTTPException(status_code=502, detail="Could not fetch SPY history from Schwab")

    try:
        result = quant.compute_twr_vs_benchmark(snapshots, spy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    quant.cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Sector exposure
# ---------------------------------------------------------------------------

@router.get("/sectors")
def get_sectors(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Approximate look-through sector exposure across holdings.
    ETF compositions come from a static table — indicative, not exact."""
    from services import sector_data

    acct = _get_brokerage(db)
    latest = db.query(func.max(Holding.snapshot_date)).filter(Holding.account_id == acct.id).scalar()
    if not latest:
        raise HTTPException(status_code=404, detail="No holdings data")
    holdings = (
        db.query(Holding)
        .filter(Holding.account_id == acct.id, Holding.snapshot_date == latest)
        .all()
    )

    sector_totals: dict[str, float] = {}
    per_holding = []
    total = 0.0
    for h in holdings:
        mv = float(h.market_value)
        total += mv
        exposure = sector_data.classify_holding(h.symbol, mv)
        for sector, dollars in exposure.items():
            sector_totals[sector] = sector_totals.get(sector, 0.0) + dollars
        per_holding.append({
            "symbol": h.symbol,
            "market_value": round(mv, 2),
            "classification": "etf_lookthrough" if h.symbol.upper() in sector_data.ETF_SECTOR_WEIGHTS
            else "stock" if h.symbol.upper() in sector_data.STOCK_SECTORS
            else "cash" if h.symbol.upper() in sector_data.MONEY_MARKET_SECTORS
            else "unclassified",
        })

    if total <= 0:
        raise HTTPException(status_code=404, detail="Portfolio value is zero")

    sectors = [
        {"sector": s, "value": round(v, 2), "pct": round(v / total * 100, 2)}
        for s, v in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True)
    ]
    unclassified_pct = next((s["pct"] for s in sectors if s["sector"] == "Unclassified"), 0.0)

    return {
        "as_of": latest.isoformat(),
        "total_value": round(total, 2),
        "sectors": sectors,
        "unclassified_pct": unclassified_pct,
        "holdings": per_holding,
    }
