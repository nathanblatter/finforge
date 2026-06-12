"""
Quantitative portfolio analytics for FinForge.

Pure-numpy/sklearn math shared by the /quant endpoints: efficient frontier,
correlation clustering, IV-vs-HV comparison, and Monte Carlo projections.
All price data comes from the Schwab market data API via services.schwab.
"""

import logging
import time
from typing import Optional

import numpy as np

from services.schwab import schwab_api_get

logger = logging.getLogger("finforge.quant")

MONEY_MARKET = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
RISK_FREE_RATE = 0.04  # annualized, used for Sharpe
TRADING_DAYS = 252

# ---------------------------------------------------------------------------
# In-memory TTL cache — quant endpoints hit Schwab hard, so results are
# cached per cache_key for CACHE_TTL seconds.
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 900  # 15 minutes


def cache_get(key: str) -> Optional[object]:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts > CACHE_TTL:
        del _cache[key]
        return None
    return value


def cache_set(key: str, value: object) -> None:
    _cache[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

async def fetch_closes(symbol: str) -> list[float]:
    """1-year daily closes for a symbol. Empty list on failure."""
    try:
        data = await schwab_api_get(
            "/pricehistory",
            params={"symbol": symbol, "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1},
            market_data=True,
        )
        return [c["close"] for c in data.get("candles", []) if c.get("close") is not None]
    except Exception as exc:
        logger.warning("[quant] Price history failed for %s: %s", symbol, exc)
        return []


async def fetch_histories(symbols: list[str]) -> dict[str, list[float]]:
    """Fetch price histories sequentially (kind to Schwab rate limits)."""
    out: dict[str, list[float]] = {}
    for sym in symbols:
        closes = await fetch_closes(sym)
        if len(closes) >= 60:
            out[sym] = closes
    return out


def aligned_returns(histories: dict[str, list[float]]) -> tuple[np.ndarray, list[str]]:
    """Build a (T, N) daily-returns matrix aligned on the trailing min length."""
    symbols = sorted(histories.keys())
    if not symbols:
        return np.array([]).reshape(0, 0), []
    min_len = min(len(histories[s]) for s in symbols)
    cols = []
    for s in symbols:
        closes = np.array(histories[s][-min_len:], dtype=float)
        cols.append(np.diff(closes) / closes[:-1])
    return np.column_stack(cols), symbols


# ---------------------------------------------------------------------------
# Efficient frontier
# ---------------------------------------------------------------------------

def compute_frontier(
    returns: np.ndarray,
    symbols: list[str],
    current_weights: dict[str, float],
    n_samples: int = 3000,
    seed: int = 42,
) -> dict:
    """Random long-only portfolio sampling + analytic stats.

    Returns frontier cloud, max-Sharpe / min-variance portfolios, and the
    current portfolio's position in risk/return space.
    """
    n = len(symbols)
    mu = returns.mean(axis=0) * TRADING_DAYS
    cov = np.cov(returns, rowvar=False) * TRADING_DAYS
    if n == 1:
        cov = cov.reshape(1, 1)

    rng = np.random.default_rng(seed)
    weights = rng.dirichlet(np.ones(n), size=n_samples)

    rets = weights @ mu
    vols = np.sqrt(np.einsum("ij,jk,ik->i", weights, cov, weights))
    vols = np.maximum(vols, 1e-9)
    sharpes = (rets - RISK_FREE_RATE) / vols

    idx_sharpe = int(np.argmax(sharpes))
    idx_minvar = int(np.argmin(vols))

    # Current portfolio point (weights over the analyzed symbols, renormalized)
    w_cur = np.array([current_weights.get(s, 0.0) for s in symbols])
    cur_total = w_cur.sum()
    current = None
    if cur_total > 0:
        w_cur = w_cur / cur_total
        cur_ret = float(w_cur @ mu)
        cur_vol = float(np.sqrt(w_cur @ cov @ w_cur))
        current = {
            "ret": round(cur_ret, 4),
            "vol": round(cur_vol, 4),
            "sharpe": round((cur_ret - RISK_FREE_RATE) / max(cur_vol, 1e-9), 4),
        }

    # Thin the cloud for the UI: keep every sample but round, the payload is small
    step = max(1, n_samples // 1500)
    cloud = [
        {"vol": round(float(v), 4), "ret": round(float(r), 4), "sharpe": round(float(s), 4)}
        for v, r, s in zip(vols[::step], rets[::step], sharpes[::step])
    ]

    def _portfolio(idx: int) -> dict:
        return {
            "ret": round(float(rets[idx]), 4),
            "vol": round(float(vols[idx]), 4),
            "sharpe": round(float(sharpes[idx]), 4),
            "weights": {s: round(float(w), 4) for s, w in zip(symbols, weights[idx]) if w > 0.005},
        }

    per_symbol = [
        {
            "symbol": s,
            "exp_return": round(float(mu[i]), 4),
            "volatility": round(float(np.sqrt(cov[i, i])), 4),
            "current_weight": round(float(w_cur[i]) if cur_total > 0 else 0.0, 4),
        }
        for i, s in enumerate(symbols)
    ]

    return {
        "symbols": symbols,
        "cloud": cloud,
        "max_sharpe": _portfolio(idx_sharpe),
        "min_variance": _portfolio(idx_minvar),
        "current": current,
        "risk_free_rate": RISK_FREE_RATE,
        "per_symbol": per_symbol,
        "lookback_days": int(returns.shape[0]),
    }


def compute_whatif(
    returns: np.ndarray,
    symbols: list[str],
    proposed_weights: dict[str, float],
    current_weights: dict[str, float],
) -> dict:
    """Risk/return/Sharpe for an arbitrary long-only weighting of the held
    symbols, alongside the current portfolio for comparison. Weights are
    renormalized, so callers can pass raw slider values."""
    mu = returns.mean(axis=0) * TRADING_DAYS
    cov = np.cov(returns, rowvar=False) * TRADING_DAYS
    if len(symbols) == 1:
        cov = cov.reshape(1, 1)

    def _point(w: np.ndarray) -> dict:
        ret = float(w @ mu)
        vol = float(max(np.sqrt(w @ cov @ w), 1e-9))
        return {
            "ret": round(ret, 4),
            "vol": round(vol, 4),
            "sharpe": round((ret - RISK_FREE_RATE) / vol, 4),
        }

    w_new = np.array([max(0.0, float(proposed_weights.get(s, 0.0))) for s in symbols])
    if w_new.sum() <= 0:
        raise ValueError("Proposed weights must include at least one held symbol")
    w_new = w_new / w_new.sum()

    w_cur = np.array([current_weights.get(s, 0.0) for s in symbols])
    if w_cur.sum() > 0:
        w_cur = w_cur / w_cur.sum()

    return {
        "symbols": symbols,
        "whatif": {
            **_point(w_new),
            "weights": {s: round(float(w), 4) for s, w in zip(symbols, w_new) if w > 0.0005},
        },
        "current": _point(w_cur) if w_cur.sum() > 0 else None,
    }


# ---------------------------------------------------------------------------
# Correlation clustering
# ---------------------------------------------------------------------------

def compute_clusters(
    returns: np.ndarray,
    symbols: list[str],
    current_weights: dict[str, float],
    corr_threshold: float = 0.65,
) -> dict:
    """Hierarchical clustering on the correlation matrix.

    Symbols whose pairwise correlation exceeds corr_threshold land in the
    same cluster — the cluster count is the portfolio's "effective" number
    of independent positions.
    """
    from sklearn.cluster import AgglomerativeClustering

    n = len(symbols)
    corr = np.corrcoef(returns, rowvar=False)
    if n == 1:
        corr = corr.reshape(1, 1)
    corr = np.nan_to_num(corr, nan=0.0)

    if n < 2:
        labels = np.zeros(n, dtype=int)
    else:
        distance = np.clip(1.0 - corr, 0.0, 2.0)
        np.fill_diagonal(distance, 0.0)
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=1.0 - corr_threshold,
        )
        labels = model.fit_predict(distance)

    clusters = []
    for label in sorted(set(labels)):
        members = [symbols[i] for i in range(n) if labels[i] == label]
        idx = [i for i in range(n) if labels[i] == label]
        if len(idx) > 1:
            sub = corr[np.ix_(idx, idx)]
            avg_corr = float((sub.sum() - len(idx)) / (len(idx) ** 2 - len(idx)))
        else:
            avg_corr = 1.0
        weight = sum(current_weights.get(s, 0.0) for s in members)
        clusters.append({
            "symbols": members,
            "weight_pct": round(weight * 100, 2),
            "avg_internal_correlation": round(avg_corr, 3),
        })
    clusters.sort(key=lambda c: c["weight_pct"], reverse=True)

    return {
        "n_positions": n,
        "n_clusters": len(clusters),
        "corr_threshold": corr_threshold,
        "clusters": clusters,
        "correlation_matrix": {
            "symbols": symbols,
            "values": [[round(float(corr[i, j]), 3) for j in range(n)] for i in range(n)],
        },
    }


# ---------------------------------------------------------------------------
# IV vs HV
# ---------------------------------------------------------------------------

def historical_vol_30d(closes: list[float]) -> Optional[float]:
    """Annualized 30-trading-day historical volatility."""
    if len(closes) < 31:
        return None
    arr = np.array(closes[-31:], dtype=float)
    rets = np.diff(arr) / arr[:-1]
    return float(np.std(rets, ddof=1) * np.sqrt(TRADING_DAYS))


def extract_atm_iv(chain: dict) -> Optional[float]:
    """Pull a ~30-day at-the-money implied vol from a Schwab options chain.

    Prefers contracts with 20–45 DTE and |delta| in [0.35, 0.65]; falls back
    to the median vol across the window. Schwab reports volatility in percent.
    """
    vols_atm: list[float] = []
    vols_any: list[float] = []

    for map_key in ("callExpDateMap", "putExpDateMap"):
        for _exp, strikes in (chain.get(map_key) or {}).items():
            for _strike, contracts in strikes.items():
                for c in contracts:
                    dte = c.get("daysToExpiration")
                    vol = c.get("volatility")
                    delta = c.get("delta")
                    if dte is None or vol is None or vol <= 0 or vol > 500:
                        continue
                    if not (20 <= dte <= 45):
                        continue
                    vols_any.append(vol)
                    if delta is not None and 0.35 <= abs(delta) <= 0.65:
                        vols_atm.append(vol)

    pool = vols_atm or vols_any
    if not pool:
        return None
    return float(np.median(pool)) / 100.0


def iv_hv_signal(iv: float, hv: float) -> str:
    if hv <= 0:
        return "UNKNOWN"
    ratio = iv / hv
    if ratio > 1.25:
        return "RICH"       # options expensive — favorable for premium selling
    if ratio < 0.80:
        return "CHEAP"      # protection/leverage is cheap
    return "FAIR"


async def fetch_options_chain(symbol: str) -> Optional[dict]:
    try:
        return await schwab_api_get(
            "/chains",
            params={"symbol": symbol, "contractType": "ALL", "strikeCount": 6, "range": "NTM"},
            market_data=True,
        )
    except Exception as exc:
        logger.warning("[quant] Options chain failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Monte Carlo projection
# ---------------------------------------------------------------------------

def monte_carlo_projection(
    portfolio_returns: np.ndarray,
    initial_value: float,
    monthly_contribution: float,
    years: int,
    target_value: Optional[float] = None,
    n_sims: int = 2000,
    seed: Optional[int] = None,
) -> dict:
    """Block-bootstrap Monte Carlo from the portfolio's own daily returns.

    Each simulated month is a resampled 21-day block compounded together, so
    fat tails and autocorrelation in the actual return history are preserved
    rather than assuming normality.
    """
    rng = np.random.default_rng(seed)
    n_days = len(portfolio_returns)
    block = 21
    months = years * 12

    if n_days < block + 1:
        raise ValueError("Insufficient return history for simulation")

    # Pre-build all monthly returns: pick random block starts, compound each block
    starts = rng.integers(0, n_days - block, size=(n_sims, months))
    log1p = np.log1p(portfolio_returns)
    cum = np.concatenate([[0.0], np.cumsum(log1p)])
    monthly = np.expm1(cum[starts + block] - cum[starts])  # (n_sims, months)

    values = np.full(n_sims, initial_value, dtype=float)
    ever_hit = np.zeros(n_sims, dtype=bool)
    yearly_percentiles = []
    for m in range(months):
        values = values * (1.0 + monthly[:, m]) + monthly_contribution
        if target_value is not None:
            ever_hit |= values >= target_value
        if (m + 1) % 12 == 0:
            p = np.percentile(values, [10, 25, 50, 75, 90])
            yearly_percentiles.append({
                "year": (m + 1) // 12,
                "p10": round(float(p[0]), 2),
                "p25": round(float(p[1]), 2),
                "p50": round(float(p[2]), 2),
                "p75": round(float(p[3]), 2),
                "p90": round(float(p[4]), 2),
            })

    result = {
        "initial_value": round(initial_value, 2),
        "monthly_contribution": round(monthly_contribution, 2),
        "years": years,
        "n_sims": n_sims,
        "yearly": yearly_percentiles,
        "final_median": yearly_percentiles[-1]["p50"] if yearly_percentiles else None,
    }
    if target_value is not None:
        result["target_value"] = round(target_value, 2)
        result["prob_hit_at_horizon"] = round(float(np.mean(values >= target_value)), 4)
        result["prob_hit_ever"] = round(float(np.mean(ever_hit)), 4)
    return result


# ---------------------------------------------------------------------------
# Covered call screening
# ---------------------------------------------------------------------------

def best_covered_call(chain: dict, target_delta: float = 0.30) -> Optional[dict]:
    """Pick the call contract closest to target delta with 20-45 DTE.

    Returns contract details + premium math, or None if the chain has no
    usable calls (e.g. mutual funds, illiquid names).
    """
    underlying = chain.get("underlyingPrice")
    best = None
    for _exp, strikes in (chain.get("callExpDateMap") or {}).items():
        for _strike, contracts in strikes.items():
            for c in contracts:
                dte = c.get("daysToExpiration")
                delta = c.get("delta")
                bid, ask = c.get("bid"), c.get("ask")
                if dte is None or delta is None or not (20 <= dte <= 45):
                    continue
                if delta <= 0 or delta > 0.6:
                    continue
                if bid is None or ask is None or bid <= 0 or ask <= 0:
                    continue
                premium = (bid + ask) / 2
                score = abs(delta - target_delta)
                if best is None or score < best["_score"]:
                    best = {
                        "_score": score,
                        "strike": c.get("strikePrice"),
                        "expiration_days": dte,
                        "delta": round(float(delta), 3),
                        "premium": round(float(premium), 2),
                        "bid": float(bid),
                        "ask": float(ask),
                        "description": c.get("description"),
                    }
    if best is None or not underlying or underlying <= 0:
        return best and None
    best.pop("_score")
    best["underlying_price"] = round(float(underlying), 2)
    best["yield_pct"] = round(best["premium"] / float(underlying) * 100, 2)
    best["annualized_yield_pct"] = round(
        best["premium"] / float(underlying) * (365 / best["expiration_days"]) * 100, 1
    )
    return best


# ---------------------------------------------------------------------------
# Benchmark comparison (time-weighted return vs SPY)
# ---------------------------------------------------------------------------

def compute_twr_vs_benchmark(
    snapshots: list[dict],
    spy_by_date: dict,
) -> dict:
    """Chain daily Modified Dietz returns from holdings snapshots.

    snapshots: [{date, value, cost_basis}] sorted ascending. The day-over-day
    change in total cost basis approximates external flows (new money in /
    proceeds out), so market return isn't polluted by contributions.
    """
    if len(snapshots) < 2:
        raise ValueError("Need at least 2 holdings snapshots for benchmark comparison")

    series = []
    port_idx = 100.0
    spy_idx = 100.0
    prev = snapshots[0]
    prev_spy = None

    # Find the SPY close at or before a date
    spy_dates = sorted(spy_by_date.keys())

    def spy_close_on(d):
        lo, hi = 0, len(spy_dates) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if spy_dates[mid] <= d:
                best = spy_dates[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return spy_by_date[best] if best is not None else None

    prev_spy = spy_close_on(prev["date"])
    series.append({"date": prev["date"].isoformat(), "portfolio": 100.0, "spy": 100.0})

    for snap in snapshots[1:]:
        v_prev, v_now = prev["value"], snap["value"]
        flow = snap["cost_basis"] - prev["cost_basis"]
        denom = v_prev + max(flow, 0.0)
        if denom > 0:
            r = (v_now - v_prev - flow) / denom
            # Guard against snapshot glitches (account transfers, bad data)
            r = max(min(r, 0.25), -0.25)
            port_idx *= 1.0 + r

        spy_now = spy_close_on(snap["date"])
        if spy_now and prev_spy and prev_spy > 0:
            spy_idx *= spy_now / prev_spy
        prev_spy = spy_now or prev_spy

        series.append({
            "date": snap["date"].isoformat(),
            "portfolio": round(port_idx, 2),
            "spy": round(spy_idx, 2),
        })
        prev = snap

    return {
        "series": series,
        "portfolio_return_pct": round(port_idx - 100.0, 2),
        "spy_return_pct": round(spy_idx - 100.0, 2),
        "excess_return_pct": round(port_idx - spy_idx, 2),
        "n_snapshots": len(snapshots),
        "start": snapshots[0]["date"].isoformat(),
        "end": snapshots[-1]["date"].isoformat(),
    }


async def fetch_spy_closes_by_date() -> dict:
    """SPY daily closes keyed by date, for benchmark alignment."""
    from datetime import datetime as _dt, timezone as _tz

    try:
        data = await schwab_api_get(
            "/pricehistory",
            params={"symbol": "SPY", "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1},
            market_data=True,
        )
    except Exception as exc:
        logger.warning("[quant] SPY history failed: %s", exc)
        return {}
    out = {}
    for c in data.get("candles", []):
        if c.get("close") is None or c.get("datetime") is None:
            continue
        d = _dt.fromtimestamp(c["datetime"] / 1000, tz=_tz.utc).date()
        out[d] = float(c["close"])
    return out
