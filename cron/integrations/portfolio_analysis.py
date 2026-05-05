"""
Portfolio analysis cron job for FinForge.

Computes per-symbol and portfolio-level risk metrics, rebalancing drift,
and tax-loss harvesting signals. Stores results in portfolio_analysis table.
"""

import json
import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import httpx
import numpy as np
from sqlalchemy import func

from config import settings
from db import (
    AccountRow,
    HoldingRow,
    MarketDataCacheRow,
    PortfolioAnalysisRow,
    PortfolioTargetRow,
    TransactionRow,
    get_session,
)
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
PORTFOLIO_SENTINEL = "__PORTFOLIO__"
MONEY_MARKET = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
TLH_THRESHOLD = Decimal("-100")  # Minimum unrealized loss to flag


def _fetch_price_history(client: httpx.Client, symbol: str) -> list[float]:
    """Fetch 1-year daily closing prices for a symbol. Returns list of close prices."""
    try:
        resp = client.get(
            "/pricehistory",
            params={
                "symbol": symbol,
                "periodType": "year",
                "period": 1,
                "frequencyType": "daily",
                "frequency": 1,
            },
        )
        if resp.status_code == 401:
            raise SchwabReauthRequired("401 during price history fetch")
        if not resp.is_success:
            logger.warning("[portfolio_analysis] Price history HTTP %d for %s", resp.status_code, symbol)
            return []
        candles = resp.json().get("candles", [])
        return [c["close"] for c in candles if c.get("close") is not None]
    except SchwabReauthRequired:
        raise
    except Exception as exc:
        logger.warning("[portfolio_analysis] Price history failed for %s: %s", symbol, exc)
        return []


def _compute_daily_returns(closes: list[float]) -> np.ndarray:
    if len(closes) < 2:
        return np.array([])
    arr = np.array(closes)
    return np.diff(arr) / arr[:-1]


def _annualized_volatility(returns: np.ndarray) -> Optional[float]:
    if len(returns) < 20:
        return None
    return float(np.std(returns, ddof=1) * np.sqrt(252))


def _compute_beta(symbol_returns: np.ndarray, market_returns: np.ndarray) -> Optional[float]:
    # Align lengths
    n = min(len(symbol_returns), len(market_returns))
    if n < 20:
        return None
    sr = symbol_returns[-n:]
    mr = market_returns[-n:]
    market_var = np.var(mr, ddof=1)
    if market_var == 0:
        return None
    cov = np.cov(sr, mr)[0, 1]
    return float(cov / market_var)


def run_portfolio_analysis() -> None:
    """Main entry point — called from cron/main.py."""
    today = date.today()

    # Get brokerage account
    with get_session() as session:
        brokerage = (
            session.query(AccountRow)
            .filter(AccountRow.alias == "Schwab Brokerage", AccountRow.is_active.is_(True))
            .first()
        )
        if not brokerage:
            logger.info("[portfolio_analysis] No active brokerage account found — skipping")
            return
        account_id = brokerage.id

        # Get latest holdings snapshot
        latest_date = (
            session.query(func.max(HoldingRow.snapshot_date))
            .filter(HoldingRow.account_id == account_id)
            .scalar()
        )
        if not latest_date:
            logger.info("[portfolio_analysis] No holdings data — skipping")
            return

        holdings = (
            session.query(HoldingRow)
            .filter(HoldingRow.account_id == account_id, HoldingRow.snapshot_date == latest_date)
            .all()
        )
        # Materialize before session closes
        holding_data = [
            {
                "symbol": h.symbol,
                "quantity": h.quantity,
                "market_value": h.market_value,
                "cost_basis": h.cost_basis,
            }
            for h in holdings
        ]

        # Get cached market data (materialize to dicts to avoid detached session errors)
        symbols = [h["symbol"] for h in holding_data]
        cache_rows = session.query(MarketDataCacheRow).filter(MarketDataCacheRow.symbol.in_(symbols)).all()
        cache_map = {
            r.symbol: {
                "last_price": float(r.last_price) if r.last_price is not None else None,
                "high_52w": float(r.high_52w) if r.high_52w is not None else None,
            }
            for r in cache_rows
        }

        # Get portfolio targets
        targets = session.query(PortfolioTargetRow).filter(PortfolioTargetRow.account_id == account_id).all()
        target_map = {t.symbol: float(t.target_pct) for t in targets}

        # Get recent investment transactions for wash sale detection (last 30 days)
        cutoff = today - timedelta(days=30)
        recent_trades = (
            session.query(TransactionRow)
            .filter(
                TransactionRow.category == "Investment Transfer",
                TransactionRow.date >= cutoff,
            )
            .all()
        )
        # Group by merchant_name (which stores the symbol)
        trade_map: dict[str, list[dict]] = {}
        for t in recent_trades:
            sym = (t.merchant_name or "").upper().strip()
            if sym:
                trade_map.setdefault(sym, []).append({
                    "date": str(t.date),
                    "action": t.subcategory or "UNKNOWN",
                    "amount": float(t.amount),
                })

    if not holding_data:
        logger.info("[portfolio_analysis] No holdings — skipping")
        return

    # Filter out money market for analysis (keep for totals)
    total_portfolio_value = sum(float(h["market_value"]) for h in holding_data)
    if total_portfolio_value <= 0:
        logger.info("[portfolio_analysis] Portfolio value is zero — skipping")
        return

    analysis_symbols = [h["symbol"] for h in holding_data if h["symbol"] not in MONEY_MARKET]

    logger.info(
        "[portfolio_analysis] Analyzing %d symbols (portfolio value: $%.2f)",
        len(analysis_symbols), total_portfolio_value,
    )

    # Fetch price history for all symbols + SPY benchmark
    try:
        token_manager = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        token_manager.load_tokens()
        access_token = token_manager.get_valid_access_token()
    except Exception as exc:
        logger.error("[portfolio_analysis] Token error: %s", exc)
        return

    price_histories: dict[str, list[float]] = {}
    returns_map: dict[str, np.ndarray] = {}

    with httpx.Client(
        base_url=SCHWAB_MARKETDATA_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    ) as client:
        # Fetch SPY first for beta calculation
        spy_closes = _fetch_price_history(client, "SPY")
        spy_returns = _compute_daily_returns(spy_closes)

        for sym in analysis_symbols:
            closes = _fetch_price_history(client, sym)
            price_histories[sym] = closes
            returns_map[sym] = _compute_daily_returns(closes)

    # Compute per-symbol metrics
    symbol_results: list[dict] = []
    vols: list[float] = []
    weights: list[float] = []

    for h in holding_data:
        sym = h["symbol"]
        mv = float(h["market_value"])
        cb = float(h["cost_basis"]) if h["cost_basis"] is not None else None
        w = mv / total_portfolio_value
        weights.append(w)

        unrealized = (mv - cb) if cb is not None else None
        is_mm = sym in MONEY_MARKET

        # Risk metrics (skip money market)
        vol = None
        beta_val = None
        if not is_mm and sym in returns_map:
            vol = _annualized_volatility(returns_map[sym])
            beta_val = _compute_beta(returns_map[sym], spy_returns)

        if vol is not None:
            vols.append(vol)
        else:
            vols.append(0.0)

        # Drawdown from 52-week high
        dd = None
        cached = cache_map.get(sym)
        if cached and cached["high_52w"] and cached["last_price"]:
            high = cached["high_52w"]
            if high > 0:
                dd = (cached["last_price"] - high) / high

        # TLH
        tlh = False
        if unrealized is not None and Decimal(str(unrealized)) < TLH_THRESHOLD and not is_mm:
            tlh = True

        # Wash sale
        ws_risk = sym in trade_map
        ws_details = json.dumps(trade_map[sym]) if ws_risk else None

        # Rebalancing
        tgt = target_map.get(sym)
        drift = (w * 100 - tgt) if tgt is not None else None

        symbol_results.append({
            "symbol": sym,
            "market_value": mv,
            "cost_basis": cb,
            "unrealized_gl": unrealized,
            "pct_of_portfolio": round(w * 100, 4),
            "target_pct": tgt,
            "drift_pct": round(drift, 4) if drift is not None else None,
            "annualized_vol": round(vol, 4) if vol is not None else None,
            "beta": round(beta_val, 4) if beta_val is not None else None,
            "drawdown_from_high": round(dd, 4) if dd is not None else None,
            "tlh_candidate": tlh,
            "wash_sale_risk": ws_risk,
            "wash_sale_details": ws_details,
        })

    # Portfolio-level metrics
    hhi = sum(w ** 2 for w in weights) * 10000
    sorted_weights = sorted(weights, reverse=True)
    top5 = sum(sorted_weights[:5]) * 100
    weighted_vol = sum(w * v for w, v in zip(weights, vols))
    min_dd = min(
        (r["drawdown_from_high"] for r in symbol_results if r["drawdown_from_high"] is not None),
        default=None,
    )

    tlh_count = sum(1 for r in symbol_results if r["tlh_candidate"])
    logger.info(
        "[portfolio_analysis] HHI=%.0f, Top5=%.1f%%, WeightedVol=%.2f%%, TLH candidates=%d",
        hhi, top5, weighted_vol * 100, tlh_count,
    )

    # Write to DB
    with get_session() as session:
        # Delete existing analysis for today
        session.query(PortfolioAnalysisRow).filter(
            PortfolioAnalysisRow.account_id == account_id,
            PortfolioAnalysisRow.analysis_date == today,
        ).delete()

        now = datetime.now(timezone.utc)

        # Per-symbol rows
        for r in symbol_results:
            session.add(PortfolioAnalysisRow(
                id=uuid.uuid4(),
                account_id=account_id,
                analysis_date=today,
                symbol=r["symbol"],
                market_value=r["market_value"],
                cost_basis=r["cost_basis"],
                unrealized_gl=r["unrealized_gl"],
                pct_of_portfolio=r["pct_of_portfolio"],
                target_pct=r["target_pct"],
                drift_pct=r["drift_pct"],
                annualized_vol=r["annualized_vol"],
                beta=r["beta"],
                drawdown_from_high=r["drawdown_from_high"],
                tlh_candidate=r["tlh_candidate"],
                wash_sale_risk=r["wash_sale_risk"],
                wash_sale_details=r["wash_sale_details"],
                created_at=now,
            ))

        # Portfolio sentinel row
        session.add(PortfolioAnalysisRow(
            id=uuid.uuid4(),
            account_id=account_id,
            analysis_date=today,
            symbol=PORTFOLIO_SENTINEL,
            hhi=round(hhi, 4),
            top5_concentration=round(top5, 4),
            weighted_volatility=round(weighted_vol, 4) if weighted_vol else None,
            max_drawdown=round(min_dd, 4) if min_dd is not None else None,
            tlh_candidate=False,
            wash_sale_risk=False,
            created_at=now,
        ))

    logger.info("[portfolio_analysis] Analysis complete — %d symbols written", len(symbol_results))

    # Queue notifications for NateBot
    try:
        from notify import queue_notification

        # TLH candidates
        tlh_syms = [r for r in symbol_results if r["tlh_candidate"]]
        if tlh_syms:
            lines = ["📉 Tax-Loss Harvesting Opportunities"]
            for r in tlh_syms:
                ws = " ⚠️WASH SALE RISK" if r["wash_sale_risk"] else ""
                lines.append(f"  {r['symbol']}: ${r['unrealized_gl']:+,.2f} unrealized loss{ws}")
            queue_notification("tlh_signal", "\n".join(lines))

        # Large drift warnings (>5%)
        drift_syms = [r for r in symbol_results if r["drift_pct"] is not None and abs(r["drift_pct"]) > 5]
        if drift_syms:
            lines = ["📊 Portfolio Drift Alert"]
            for r in drift_syms:
                action = "overweight" if r["drift_pct"] > 0 else "underweight"
                lines.append(f"  {r['symbol']}: {r['drift_pct']:+.1f}% ({action})")
            queue_notification("portfolio_drift", "\n".join(lines))
    except Exception:
        pass
