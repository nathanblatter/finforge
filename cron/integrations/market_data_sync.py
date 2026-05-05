"""
Market data sync for FinForge.

Collects all distinct symbols from watchlist_items and holdings (latest snapshot),
fetches quotes from Schwab in batches of 50, and upserts into market_data_cache.
"""

import logging
import uuid
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import func

from config import settings
from db import HoldingRow, MarketDataCacheRow, WatchlistItemRow, get_session
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
BATCH_SIZE = 50


def _collect_symbols() -> set[str]:
    """Get all distinct symbols from watchlist_items + latest holdings snapshot."""
    symbols: set[str] = set()

    with get_session() as session:
        # All watchlist symbols
        wl_symbols = session.query(WatchlistItemRow.symbol).distinct().all()
        for (sym,) in wl_symbols:
            if sym:
                symbols.add(sym.upper())

        # Latest holdings snapshot date
        latest_date = session.query(func.max(HoldingRow.snapshot_date)).scalar()
        if latest_date:
            holding_symbols = (
                session.query(HoldingRow.symbol)
                .filter(HoldingRow.snapshot_date == latest_date)
                .distinct()
                .all()
            )
            for (sym,) in holding_symbols:
                if sym:
                    symbols.add(sym.upper())

    return symbols


def _fetch_quotes_batch(
    client: httpx.Client, symbols: list[str]
) -> dict:
    """Fetch quotes for a batch of symbols."""
    symbols_str = ",".join(symbols)
    response = client.get(
        "/quotes",
        params={"symbols": symbols_str, "fields": "quote,fundamental"},
    )
    if response.status_code == 401:
        raise SchwabReauthRequired("401 during market data fetch")
    response.raise_for_status()
    return response.json()


def _upsert_quotes(quotes_data: dict) -> int:
    """Upsert quote data into market_data_cache. Returns count of rows written."""
    now = datetime.now(timezone.utc)
    count = 0

    with get_session() as session:
        for symbol, info in quotes_data.items():
            q = info.get("quote", {})
            f = info.get("fundamental", {})

            # Delete existing row for this symbol
            session.query(MarketDataCacheRow).filter_by(symbol=symbol).delete()

            row = MarketDataCacheRow(
                id=uuid.uuid4(),
                symbol=symbol,
                last_price=q.get("lastPrice"),
                open_price=q.get("openPrice"),
                high_price=q.get("highPrice"),
                low_price=q.get("lowPrice"),
                close_price=q.get("closePrice"),
                volume=q.get("totalVolume"),
                net_change=q.get("netChange"),
                net_change_pct=q.get("netPercentChangeInDouble"),
                high_52w=q.get("52WkHigh"),
                low_52w=q.get("52WkLow"),
                pe_ratio=f.get("peRatio"),
                dividend_yield=f.get("divYield"),
                fetched_at=now,
            )
            session.add(row)
            count += 1

    return count


def run_market_data_sync() -> None:
    """Main entry point — called from cron/main.py."""
    symbols = _collect_symbols()
    if not symbols:
        logger.info("[market_data_sync] No symbols to sync — skipping")
        return

    logger.info("[market_data_sync] Syncing %d symbols", len(symbols))

    try:
        token_manager = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        token_manager.load_tokens()
    except FileNotFoundError:
        logger.error(
            "[market_data_sync] Token file not found at %s. "
            "Run the Schwab OAuth setup flow first.",
            settings.schwab_token_file,
        )
        return
    except Exception as exc:
        logger.error("[market_data_sync] Failed to load Schwab tokens: %s", exc)
        return

    # Ensure we have a valid access token
    try:
        access_token = token_manager.get_valid_access_token()
    except SchwabReauthRequired:
        logger.critical("[market_data_sync] Schwab re-authentication required. Sync aborted.")
        return
    except Exception as exc:
        logger.error("[market_data_sync] Token refresh failed: %s", exc)
        return

    symbol_list = sorted(symbols)
    batches = [symbol_list[i : i + BATCH_SIZE] for i in range(0, len(symbol_list), BATCH_SIZE)]
    total_written = 0

    with httpx.Client(
        base_url=SCHWAB_MARKETDATA_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    ) as client:
        for batch in batches:
            try:
                data = _fetch_quotes_batch(client, batch)
                written = _upsert_quotes(data)
                total_written += written
            except SchwabReauthRequired:
                logger.critical("[market_data_sync] Schwab re-auth required. Aborting remaining batches.")
                return
            except Exception as exc:
                logger.error("[market_data_sync] Batch failed (%s): %s", batch[:3], exc)

    logger.info("[market_data_sync] Done — %d quotes cached", total_written)
