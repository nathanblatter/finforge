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
