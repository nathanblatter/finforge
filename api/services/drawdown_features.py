"""
Drawdown model feature computation for API-side inference.

KEEP IN SYNC with cron/integrations/drawdown_model.py compute_features().
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

MODEL_PATH = "/secrets/drawdown_model.pkl"
META_PATH = "/secrets/drawdown_model_meta.json"
WARMUP_DAYS = 50

# Module-level cache
_cached_model = None
_cached_meta = None
_cache_time = 0.0
_CACHE_TTL = 300  # 5 minutes


def _sma(arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full_like(arr, np.nan)
    cumsum = np.cumsum(arr)
    out[window - 1 :] = (cumsum[window - 1 :] - np.concatenate([[0], cumsum[:-window]])) / window
    return out


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full_like(arr, np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = np.std(arr[i - window + 1 : i + 1], ddof=1)
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.full(len(closes), np.nan)
    avg_loss = np.full(len(closes), np.nan)

    if len(gains) < period:
        return avg_gain

    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_features(
    closes: np.ndarray,
    volumes: np.ndarray,
    high_52w: Optional[float] = None,
    pe_ratio: Optional[float] = None,
    dividend_yield: Optional[float] = None,
) -> np.ndarray:
    """Compute feature matrix. Returns (n_days, 14) array.

    KEEP IN SYNC with cron/integrations/drawdown_model.py
    """
    n = len(closes)
    if n < WARMUP_DAYS + 5:
        return np.array([]).reshape(0, 14)

    # If high_52w not provided, compute from the closes array
    if high_52w is None and n >= 252:
        high_52w = float(np.max(closes[-252:]))
    elif high_52w is None:
        high_52w = float(np.max(closes))

    returns = np.diff(closes) / closes[:-1]
    returns = np.concatenate([[0.0], returns])

    rsi_14 = _rsi(closes, 14)
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    std20 = _rolling_std(closes, 20)
    vol_sma20 = _sma(volumes, 20)
    vol_10d = _rolling_std(returns, 10)
    vol_30d = _rolling_std(returns, 30)

    features = np.full((n, 14), np.nan)

    for i in range(WARMUP_DAYS, n):
        features[i, 0] = rsi_14[i] if not np.isnan(rsi_14[i]) else 50.0
        features[i, 1] = closes[i] / sma20[i] if sma20[i] and sma20[i] > 0 else 1.0
        features[i, 2] = closes[i] / sma50[i] if sma50[i] and sma50[i] > 0 else 1.0
        features[i, 3] = (closes[i] - sma20[i]) / (2 * std20[i]) if std20[i] and std20[i] > 0 else 0.0
        features[i, 4] = (closes[i] - closes[i - 5]) / closes[i - 5] if closes[i - 5] > 0 else 0.0
        features[i, 5] = (closes[i] - closes[i - 20]) / closes[i - 20] if closes[i - 20] > 0 else 0.0
        features[i, 6] = np.mean(np.abs(returns[i - 13 : i + 1]))
        features[i, 7] = vol_10d[i] if not np.isnan(vol_10d[i]) else 0.0
        features[i, 8] = vol_30d[i] if not np.isnan(vol_30d[i]) else 0.0
        features[i, 9] = (vol_10d[i] / vol_30d[i]) if vol_30d[i] and vol_30d[i] > 0 and not np.isnan(vol_30d[i]) else 1.0
        features[i, 10] = (volumes[i] / vol_sma20[i]) if vol_sma20[i] and vol_sma20[i] > 0 else 1.0
        features[i, 11] = (closes[i] - high_52w) / high_52w if high_52w and high_52w > 0 else 0.0
        features[i, 12] = pe_ratio if pe_ratio is not None else 0.0
        features[i, 13] = dividend_yield if dividend_yield is not None else 0.0

    return features


def load_model():
    """Load model and metadata with caching."""
    global _cached_model, _cached_meta, _cache_time

    now = time.time()
    if _cached_model is not None and (now - _cache_time) < _CACHE_TTL:
        return _cached_model, _cached_meta

    if not Path(MODEL_PATH).exists():
        return None, None

    _cached_model = joblib.load(MODEL_PATH)
    _cached_meta = {}
    if Path(META_PATH).exists():
        with open(META_PATH) as f:
            _cached_meta = json.load(f)
    _cache_time = now
    return _cached_model, _cached_meta
