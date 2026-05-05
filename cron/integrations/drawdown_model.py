"""
Drawdown prediction model for FinForge.

Trains a GradientBoostingClassifier to predict whether a symbol will
drop >5% from current price within the next 30 calendar days.

Model is persisted to /secrets/drawdown_model.pkl.
Feature computation is pure numpy — duplicated in api/services/drawdown_features.py.
"""

import json
import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

from config import settings
from db import AccountRow, DrawdownPredictionRow, get_session
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
MODEL_PATH = "/secrets/drawdown_model.pkl"
META_PATH = "/secrets/drawdown_model_meta.json"
DRAWDOWN_THRESHOLD = 0.95  # 5% drop
LOOKAHEAD_DAYS = 21  # ~30 calendar days in trading days
WARMUP_DAYS = 50  # SMA50 needs 50 days

# Diversified training universe — liquid large caps across sectors
TRAINING_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "BRK.B",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "DIS", "BAC", "XOM",
    "PFE", "KO", "PEP", "CSCO", "ADBE", "CRM", "NFLX", "AMD", "INTC",
    "QCOM", "TXN", "AVGO", "COST", "ABT", "TMO", "MRK", "LLY", "UNH",
    "CVX", "MCD", "NKE", "LOW", "CAT", "GS", "AXP", "DE", "RTX",
    "SPY", "QQQ", "IWM", "VTI", "VOO",
]


# ---------------------------------------------------------------------------
# Feature engineering (KEEP IN SYNC with api/services/drawdown_features.py)
# ---------------------------------------------------------------------------

def _sma(arr: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average. Returns array of same length, NaN for first window-1 elements."""
    out = np.full_like(arr, np.nan)
    cumsum = np.cumsum(arr)
    out[window - 1 :] = (cumsum[window - 1 :] - np.concatenate([[0], cumsum[:-window]])) / window
    return out


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling standard deviation of array."""
    out = np.full_like(arr, np.nan)
    for i in range(window - 1, len(arr)):
        out[i] = np.std(arr[i - window + 1 : i + 1], ddof=1)
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
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
    """Compute feature matrix from price/volume data. Returns (n_days, 14) array.

    KEEP IN SYNC with api/services/drawdown_features.py
    """
    n = len(closes)
    if n < WARMUP_DAYS + 5:
        return np.array([]).reshape(0, 14)

    # If high_52w not provided, compute from the closes array (rolling 252-day max)
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
        # Price-based
        features[i, 0] = rsi_14[i] if not np.isnan(rsi_14[i]) else 50.0
        features[i, 1] = closes[i] / sma20[i] if sma20[i] and sma20[i] > 0 else 1.0
        features[i, 2] = closes[i] / sma50[i] if sma50[i] and sma50[i] > 0 else 1.0
        features[i, 3] = (closes[i] - sma20[i]) / (2 * std20[i]) if std20[i] and std20[i] > 0 else 0.0

        # Rate of change
        features[i, 4] = (closes[i] - closes[i - 5]) / closes[i - 5] if closes[i - 5] > 0 else 0.0
        features[i, 5] = (closes[i] - closes[i - 20]) / closes[i - 20] if closes[i - 20] > 0 else 0.0

        # ATR proxy (avg absolute daily change over 14 days)
        features[i, 6] = np.mean(np.abs(returns[i - 13 : i + 1]))

        # Volatility
        features[i, 7] = vol_10d[i] if not np.isnan(vol_10d[i]) else 0.0
        features[i, 8] = vol_30d[i] if not np.isnan(vol_30d[i]) else 0.0
        features[i, 9] = (vol_10d[i] / vol_30d[i]) if vol_30d[i] and vol_30d[i] > 0 and not np.isnan(vol_30d[i]) else 1.0

        # Volume
        features[i, 10] = (volumes[i] / vol_sma20[i]) if vol_sma20[i] and vol_sma20[i] > 0 else 1.0

        # Drawdown from 52w high
        features[i, 11] = (closes[i] - high_52w) / high_52w if high_52w and high_52w > 0 else 0.0

        # Fundamentals (static)
        features[i, 12] = pe_ratio if pe_ratio is not None else 0.0
        features[i, 13] = dividend_yield if dividend_yield is not None else 0.0

    return features


def construct_labels(closes: np.ndarray, lookahead: int = LOOKAHEAD_DAYS) -> np.ndarray:
    """Binary labels: 1 if min future price drops >5% from current within lookahead days."""
    n = len(closes)
    labels = np.full(n, np.nan)
    for i in range(n - lookahead):
        future_min = np.min(closes[i + 1 : i + 1 + lookahead])
        labels[i] = 1.0 if (future_min / closes[i]) < DRAWDOWN_THRESHOLD else 0.0
    return labels


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_candles(client: httpx.Client, symbol: str) -> tuple[np.ndarray, np.ndarray]:
    """Fetch 1-year OHLCV, return (closes, volumes) arrays."""
    try:
        resp = client.get(
            "/pricehistory",
            params={"symbol": symbol, "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1},
        )
        if resp.status_code == 401:
            raise SchwabReauthRequired("401")
        if not resp.is_success:
            return np.array([]), np.array([])
        candles = resp.json().get("candles", [])
        closes = np.array([c["close"] for c in candles if c.get("close") is not None], dtype=float)
        volumes = np.array([c.get("volume", 0) for c in candles], dtype=float)
        return closes, volumes
    except SchwabReauthRequired:
        raise
    except Exception as exc:
        logger.debug("[drawdown_model] Fetch failed for %s: %s", symbol, exc)
        return np.array([]), np.array([])


def _fetch_quotes_batch(client: httpx.Client, symbols: list[str]) -> dict:
    """Fetch quotes for batch of symbols."""
    resp = client.get("/quotes", params={"symbols": ",".join(symbols), "fields": "quote,fundamental"})
    if resp.status_code == 401:
        raise SchwabReauthRequired("401")
    if not resp.is_success:
        return {}
    return resp.json()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_and_persist() -> None:
    """Fetch data, engineer features, train model, persist to disk."""
    logger.info("[drawdown_model] Starting training on %d symbols", len(TRAINING_UNIVERSE))

    try:
        tm = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        tm.load_tokens()
        access_token = tm.get_valid_access_token()
    except Exception as exc:
        logger.error("[drawdown_model] Token error: %s", exc)
        return

    all_X = []
    all_y = []

    with httpx.Client(
        base_url=SCHWAB_MARKETDATA_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    ) as client:
        # Fetch quotes in batches for fundamentals
        quote_data: dict = {}
        for i in range(0, len(TRAINING_UNIVERSE), 50):
            batch = TRAINING_UNIVERSE[i : i + 50]
            try:
                qd = _fetch_quotes_batch(client, batch)
                quote_data.update(qd)
            except SchwabReauthRequired:
                logger.critical("[drawdown_model] Re-auth required during quote fetch")
                return
            time.sleep(0.2)

        # Fetch price history per symbol
        for sym in TRAINING_UNIVERSE:
            closes, volumes = _fetch_candles(client, sym)
            if len(closes) < WARMUP_DAYS + LOOKAHEAD_DAYS + 20:
                logger.debug("[drawdown_model] Skipping %s — insufficient data (%d days)", sym, len(closes))
                continue

            # Extract fundamentals
            qi = quote_data.get(sym, {})
            q = qi.get("quote", {})
            f = qi.get("fundamental", {})
            high_52w = q.get("52WkHigh")
            pe = f.get("peRatio")
            dy = f.get("divYield")

            features = compute_features(closes, volumes, high_52w, pe, dy)
            labels = construct_labels(closes)

            # Keep only rows where both features and labels are valid
            valid = ~np.isnan(features).any(axis=1) & ~np.isnan(labels)
            if valid.sum() < 20:
                continue

            all_X.append(features[valid])
            all_y.append(labels[valid])

            time.sleep(0.1)  # Rate limit

    if not all_X:
        logger.error("[drawdown_model] No training data collected")
        return

    X = np.vstack(all_X)
    y = np.concatenate(all_y)
    logger.info("[drawdown_model] Training set: %d samples, %.1f%% positive", len(y), y.mean() * 100)

    # Shuffle-based split with stratification for better generalization
    # Temporal split causes regime-dependent overfitting with limited data
    from sklearn.model_selection import train_test_split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y,
    )

    model = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=20,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_val)
    y_proba = model.predict_proba(X_val)[:, 1]
    acc = accuracy_score(y_val, y_pred)
    prec = precision_score(y_val, y_pred, zero_division=0)
    rec = recall_score(y_val, y_pred, zero_division=0)
    auc = roc_auc_score(y_val, y_proba) if len(np.unique(y_val)) > 1 else 0.0

    logger.info(
        "[drawdown_model] Validation — AUC=%.3f Acc=%.3f Prec=%.3f Rec=%.3f",
        auc, acc, prec, rec,
    )

    # Feature importances
    feature_names = [
        "rsi_14", "price_sma20_ratio", "price_sma50_ratio", "bollinger_pos",
        "roc_5", "roc_20", "atr_14", "vol_10d", "vol_30d", "vol_ratio",
        "volume_ratio", "drawdown_52w", "pe_ratio", "dividend_yield",
    ]
    importances = model.feature_importances_
    top_features = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)[:5]
    logger.info("[drawdown_model] Top features: %s", ", ".join(f"{n}={v:.3f}" for n, v in top_features))

    # Persist
    joblib.dump(model, MODEL_PATH)
    trained_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "trained_at": trained_at,
        "n_samples": int(len(y)),
        "n_positive": int(y.sum()),
        "positive_rate": round(float(y.mean()), 4),
        "val_auc": round(auc, 4),
        "val_accuracy": round(acc, 4),
        "val_precision": round(prec, 4),
        "val_recall": round(rec, 4),
        "feature_names": feature_names,
        "top_features": [{"name": n, "importance": round(float(v), 4)} for n, v in top_features],
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("[drawdown_model] Model saved to %s", MODEL_PATH)

    # Run predictions on held symbols and queue alerts for high-risk positions
    try:
        from db import HoldingRow, MarketDataCacheRow, DrawdownPredictionRow, get_session as gs2
        from sqlalchemy import func as sqlfunc

        with gs2() as session:
            acct = session.query(AccountRow).filter(
                AccountRow.alias == "Schwab Brokerage", AccountRow.is_active.is_(True)
            ).first()
            if acct:
                latest_date = session.query(sqlfunc.max(HoldingRow.snapshot_date)).filter(
                    HoldingRow.account_id == acct.id
                ).scalar()
                if latest_date:
                    held = [r[0] for r in session.query(HoldingRow.symbol).filter(
                        HoldingRow.account_id == acct.id, HoldingRow.snapshot_date == latest_date
                    ).distinct().all()]

                    warnings = []
                    today_date = date.today()
                    with httpx.Client(
                        base_url=SCHWAB_MARKETDATA_BASE,
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=30,
                    ) as pred_client:
                        # Fetch quotes for fundamentals
                        held_quotes = {}
                        if held:
                            try:
                                held_quotes = _fetch_quotes_batch(pred_client, held)
                            except Exception:
                                pass

                        for sym in held:
                            closes_h, volumes_h = _fetch_candles(pred_client, sym)
                            if len(closes_h) < WARMUP_DAYS + 5:
                                continue
                            qi_h = held_quotes.get(sym, {})
                            q_h = qi_h.get("quote", {})
                            f_h = qi_h.get("fundamental", {})
                            feat = compute_features(closes_h, volumes_h, q_h.get("52WkHigh"), f_h.get("peRatio"), f_h.get("divYield"))
                            if len(feat) == 0 or np.isnan(feat[-1]).any():
                                continue
                            latest_f = np.nan_to_num(feat[-1:], nan=0.0)
                            prob = float(model.predict_proba(latest_f)[0, 1])

                            # Cache prediction
                            existing = session.query(DrawdownPredictionRow).filter_by(
                                symbol=sym, prediction_date=today_date
                            ).first()
                            if existing:
                                existing.drawdown_probability = round(prob, 4)
                                existing.model_version = trained_at
                            else:
                                session.add(DrawdownPredictionRow(
                                    id=uuid.uuid4(), symbol=sym, prediction_date=today_date,
                                    drawdown_probability=round(prob, 4), model_version=trained_at,
                                ))

                            if prob > 0.6:
                                warnings.append((sym, prob))
                            time.sleep(0.1)

                    if warnings:
                        from notify import queue_notification
                        lines = ["🔮 Drawdown Risk Alert"]
                        for sym, prob in sorted(warnings, key=lambda x: x[1], reverse=True):
                            level = "VERY HIGH" if prob > 0.6 else "HIGH"
                            lines.append(f"  {sym}: {prob*100:.0f}% probability of >5% drop ({level})")
                        queue_notification("drawdown_warning", "\n".join(lines), priority="urgent")

        logger.info("[drawdown_model] Post-training predictions complete")
    except Exception as exc:
        logger.warning("[drawdown_model] Post-training prediction failed: %s", exc)
