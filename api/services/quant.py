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
