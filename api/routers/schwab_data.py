"""Schwab Trader API data endpoints — accounts, positions, market data."""

import logging
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth import require_auth
from services.schwab import get_access_token, schwab_api_get

logger = logging.getLogger("finforge.schwab_data")

router = APIRouter(prefix="/schwab", tags=["schwab-data"])


# ---------------------------------------------------------------------------
# Accounts & Positions
# ---------------------------------------------------------------------------

@router.get("/accounts")
async def get_accounts(_: dict = Depends(require_auth)):
    """Fetch all Schwab accounts with balances and positions."""
    try:
        data = await schwab_api_get("/accounts", params={"fields": "positions"})
        # Strip raw account numbers, return only what we need
        accounts = []
        for acct in data:
            sa = acct.get("securitiesAccount", {})
            balances = sa.get("currentBalances", {})
            positions = sa.get("positions", [])

            acct_type = sa.get("type", "UNKNOWN")
            if "IRA" in acct_type.upper() or "ROTH" in acct_type.upper():
                alias = "Schwab Roth IRA"
            else:
                alias = "Schwab Brokerage"

            holdings = []
            for pos in positions:
                inst = pos.get("instrument", {})
                holdings.append({
                    "symbol": inst.get("symbol"),
                    "asset_type": inst.get("assetType"),
                    "quantity": pos.get("longQuantity", 0),
                    "market_value": pos.get("marketValue", 0),
                    "average_price": pos.get("averagePrice"),
                    "current_day_pl": pos.get("currentDayProfitLoss", 0),
                    "current_day_pl_pct": pos.get("currentDayProfitLossPercentage", 0),
                })

            accounts.append({
                "alias": alias,
                "account_type": acct_type,
                "liquidation_value": balances.get("liquidationValue", 0),
                "cash_balance": balances.get("cashBalance", 0),
                "equity": balances.get("equity", 0),
                "long_market_value": balances.get("longMarketValue", 0),
                "positions": holdings,
            })

        return {"accounts": accounts}
    except Exception as exc:
        logger.exception("Failed to fetch Schwab accounts")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ---------------------------------------------------------------------------
# Market Data — Quotes
# ---------------------------------------------------------------------------

@router.get("/quotes")
async def get_quotes(
    symbols: str = Query(..., description="Comma-separated ticker symbols (e.g. AAPL,MSFT,VOO)"),
    _: dict = Depends(require_auth),
):
    """Get real-time quotes for one or more symbols."""
    try:
        data = await schwab_api_get(
            "/quotes",
            params={"symbols": symbols, "fields": "quote,fundamental"},
            market_data=True,
        )
        quotes = {}
        for symbol, info in data.items():
            q = info.get("quote", {})
            f = info.get("fundamental", {})
            quotes[symbol] = {
                "symbol": symbol,
                "last_price": q.get("lastPrice"),
                "open": q.get("openPrice"),
                "high": q.get("highPrice"),
                "low": q.get("lowPrice"),
                "close": q.get("closePrice"),
                "volume": q.get("totalVolume"),
                "net_change": q.get("netChange"),
                "net_change_pct": q.get("netPercentChangeInDouble"),
                "52_week_high": q.get("52WkHigh"),
                "52_week_low": q.get("52WkLow"),
                "pe_ratio": f.get("peRatio"),
                "dividend_yield": f.get("divYield"),
                "market_cap": f.get("marketCap"),
            }
        return {"quotes": quotes}
    except Exception as exc:
        logger.exception("Failed to fetch quotes")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ---------------------------------------------------------------------------
# Market Data — Price History
# ---------------------------------------------------------------------------

@router.get("/pricehistory/{symbol}")
async def get_price_history(
    symbol: str,
    period_type: str = Query("month", description="day, month, year, ytd"),
    period: int = Query(1, description="Number of periods"),
    frequency_type: str = Query("daily", description="minute, daily, weekly, monthly"),
    frequency: int = Query(1, description="Frequency interval"),
    _: dict = Depends(require_auth),
):
    """Get historical price data for a symbol."""
    try:
        data = await schwab_api_get(
            "/pricehistory",
            params={
                "symbol": symbol,
                "periodType": period_type,
                "period": period,
                "frequencyType": frequency_type,
                "frequency": frequency,
            },
            market_data=True,
        )
        candles = data.get("candles", [])
        return {
            "symbol": symbol,
            "candle_count": len(candles),
            "candles": [
                {
                    "date": datetime.fromtimestamp(c["datetime"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "open": c.get("open"),
                    "high": c.get("high"),
                    "low": c.get("low"),
                    "close": c.get("close"),
                    "volume": c.get("volume"),
                }
                for c in candles
            ],
        }
    except Exception as exc:
        logger.exception("Failed to fetch price history for %s", symbol)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ---------------------------------------------------------------------------
# Market Data — Movers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Market Data — Options Chain
# ---------------------------------------------------------------------------

@router.get("/options/{symbol}")
async def get_options_chain(
    symbol: str,
    contract_type: str = Query("ALL", description="ALL, CALL, or PUT"),
    strike_count: int = Query(10, description="Number of strikes around ATM"),
    _: dict = Depends(require_auth),
):
    """Get options chain for a symbol from Schwab."""
    try:
        data = await schwab_api_get(
            "/chains",
            params={
                "symbol": symbol.upper(),
                "contractType": contract_type,
                "strikeCount": strike_count,
            },
            market_data=True,
        )
        return data
    except Exception as exc:
        logger.exception("Failed to fetch options chain for %s", symbol)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.get("/movers/{index}")
async def get_movers(
    index: str = "$SPX.X",
    direction: str = Query("up", description="up or down"),
    change: str = Query("percent", description="percent or value"),
    _: dict = Depends(require_auth),
):
    """Get top movers for an index."""
    try:
        data = await schwab_api_get(
            f"/movers/{index}",
            params={"direction": direction, "change": change},
            market_data=True,
        )
        return data
    except Exception as exc:
        logger.exception("Failed to fetch movers for %s", index)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
