"""
Market regime detection for FinForge.

Classifies the current market environment from SPY daily price action:

  bull_quiet     — uptrend, low volatility
  bull_volatile  — uptrend, elevated volatility
  bear_volatile  — downtrend, elevated volatility
  bear_quiet     — downtrend, low volatility (grinding decline)
  choppy         — no clear trend

The drawdown alert threshold is conditioned on this regime: warnings fire
earlier in volatile/bear regimes and later in quiet bull markets.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx
import numpy as np

from config import settings
from db import MarketRegimeRow, get_session
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger("finforge.cron.market_regime")

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
VOL_THRESHOLD = 0.18      # annualized 20d vol above this = "volatile"
TREND_THRESHOLD = 0.02    # |60d return| below this = "choppy"

# Drawdown-alert probability thresholds per regime
REGIME_ALERT_THRESHOLDS = {
    "bull_quiet": 0.70,
    "bull_volatile": 0.60,
    "choppy": 0.60,
    "bear_quiet": 0.55,
    "bear_volatile": 0.50,
}
DEFAULT_ALERT_THRESHOLD = 0.60


def classify(closes: np.ndarray) -> Optional[dict]:
    """Classify regime from >= 70 days of SPY closes."""
    if len(closes) < 70:
        return None

    returns = np.diff(closes) / closes[:-1]
    vol_20d = float(np.std(returns[-20:], ddof=1) * np.sqrt(252))
    trend_60d = float(closes[-1] / closes[-61] - 1.0)
    sma20 = float(np.mean(closes[-20:]))
    sma50 = float(np.mean(closes[-50:]))
    sma_ratio = sma20 / sma50 if sma50 > 0 else 1.0

    volatile = vol_20d > VOL_THRESHOLD
    if abs(trend_60d) < TREND_THRESHOLD and abs(sma_ratio - 1.0) < 0.01:
        regime = "choppy"
    elif trend_60d >= 0 and sma_ratio >= 1.0:
        regime = "bull_volatile" if volatile else "bull_quiet"
    elif trend_60d < 0 and sma_ratio < 1.0:
        regime = "bear_volatile" if volatile else "bear_quiet"
    else:
        regime = "choppy"  # trend and moving averages disagree

    return {
        "regime": regime,
        "realized_vol_20d": round(vol_20d, 4),
        "trend_60d": round(trend_60d, 4),
        "sma20_vs_sma50": round(sma_ratio, 4),
    }


def get_latest_regime() -> Optional[str]:
    """Most recent stored regime, for other jobs to condition on."""
    try:
        with get_session() as session:
            row = (
                session.query(MarketRegimeRow)
                .order_by(MarketRegimeRow.regime_date.desc())
                .first()
            )
            return row.regime if row else None
    except Exception:
        return None


def get_drawdown_alert_threshold() -> float:
    """Regime-conditioned probability threshold for drawdown warnings."""
    regime = get_latest_regime()
    return REGIME_ALERT_THRESHOLDS.get(regime, DEFAULT_ALERT_THRESHOLD)


def run_market_regime() -> None:
    today = date.today()

    try:
        tm = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        tm.load_tokens()
        access_token = tm.get_valid_access_token()
    except SchwabReauthRequired:
        logger.critical("[market_regime] Schwab re-auth required — skipping")
        return
    except Exception as exc:
        logger.error("[market_regime] Token error: %s", exc)
        return

    try:
        with httpx.Client(
            base_url=SCHWAB_MARKETDATA_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        ) as client:
            resp = client.get(
                "/pricehistory",
                params={"symbol": "SPY", "periodType": "year", "period": 1,
                        "frequencyType": "daily", "frequency": 1},
            )
            resp.raise_for_status()
            closes = np.array(
                [c["close"] for c in resp.json().get("candles", []) if c.get("close") is not None],
                dtype=float,
            )
    except Exception as exc:
        logger.error("[market_regime] SPY price history failed: %s", exc)
        return

    result = classify(closes)
    if result is None:
        logger.warning("[market_regime] Insufficient SPY history (%d days)", len(closes))
        return

    previous = get_latest_regime()

    with get_session() as session:
        session.query(MarketRegimeRow).filter_by(regime_date=today).delete()
        session.add(MarketRegimeRow(
            id=uuid.uuid4(),
            regime_date=today,
            regime=result["regime"],
            realized_vol_20d=Decimal(str(result["realized_vol_20d"])),
            trend_60d=Decimal(str(result["trend_60d"])),
            sma20_vs_sma50=Decimal(str(result["sma20_vs_sma50"])),
            created_at=datetime.now(timezone.utc),
        ))

    logger.info(
        "[market_regime] %s (vol=%.1f%%, trend=%.1f%%, sma_ratio=%.3f)",
        result["regime"], result["realized_vol_20d"] * 100,
        result["trend_60d"] * 100, result["sma20_vs_sma50"],
    )

    if previous and previous != result["regime"]:
        try:
            from notify import queue_notification
            labels = {
                "bull_quiet": "🟢 Bull / Low Vol",
                "bull_volatile": "🟡 Bull / High Vol",
                "bear_quiet": "🟠 Bear / Low Vol",
                "bear_volatile": "🔴 Bear / High Vol",
                "choppy": "⚪️ Choppy / No Trend",
            }
            queue_notification(
                "market_regime",
                f"📊 Market regime change: {labels.get(previous, previous)} → "
                f"{labels.get(result['regime'], result['regime'])}\n"
                f"SPY 20d vol {result['realized_vol_20d']*100:.0f}%, "
                f"60d return {result['trend_60d']*100:+.1f}%",
                priority="normal",
            )
        except Exception:
            pass
