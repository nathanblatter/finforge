"""
Schwab Trader API sync for FinForge.

Syncs balances, positions, and investment transactions for:
  - Schwab Brokerage  (brokerage / Charles Schwab)
  - Schwab Roth IRA   (ira / Charles Schwab)

OAuth tokens are managed by SchwabTokenManager — stored in a file on disk,
never in the database. Account hashes (Schwab's obfuscated account identifier)
are also stored in the token file, not the DB.

PRD requirements implemented:
  - /accounts             → balance snapshots (liquidationValue as portfolio_value)
  - /accounts/{hash}/positions → holdings snapshot for today
  - /accounts/{hash}/orders    → filled investment transactions (last 90 days)
  - Force token refresh on every nightly run (rolls 7-day refresh token window)
  - SchwabReauthRequired → CRITICAL log (DB alert wired in Phase 5)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from config import settings
from db import (
    BalanceRow,
    DividendTransactionRow,
    HoldingRow,
    TransactionRow,
    get_session,
    get_or_create_account,
)
from etl.deidentify import deidentify_schwab_balance, deidentify_schwab_position
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
SCHWAB_ORDERS_LOOKBACK_DAYS = 90
# Dividends are infrequent (usually quarterly) — look back far enough to infer
# cadence and a raise/cut history even for a newly-added holding.
SCHWAB_DIVIDENDS_LOOKBACK_DAYS = 730

# ---------------------------------------------------------------------------
# Account config — alias → (account_type, institution)
# ---------------------------------------------------------------------------

SCHWAB_ACCOUNTS: dict[str, tuple[str, str]] = {
    "Schwab Brokerage": ("brokerage", "Charles Schwab"),
    "Schwab Roth IRA": ("ira", "Charles Schwab"),
}


def _load_account_number_to_alias() -> dict[str, str]:
    """Load account number → alias mapping from SCHWAB_ACCOUNT_MAP env var.
    Expected format: JSON object {"account_number": "alias", ...}"""
    raw = settings.schwab_account_map
    if not raw:
        logger.error(
            "[schwab_sync] SCHWAB_ACCOUNT_MAP env var is not set. "
            "Set it to a JSON object mapping account numbers to aliases."
        )
        return {}
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_schwab_sync() -> None:
    """
    Main entry point for the Schwab sync job (called from cron/main.py).
    Forces a token refresh, then syncs accounts, positions, and orders.
    """
    try:
        token_manager = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        token_manager.load_tokens()
    except FileNotFoundError:
        logger.error(
            "[schwab_sync] Token file not found at %s. "
            "Run the Schwab OAuth setup flow first.",
            settings.schwab_token_file,
        )
        return
    except Exception as exc:
        logger.error("[schwab_sync] Failed to load Schwab tokens: %s", exc)
        return

    try:
        # Always force-refresh to roll the 7-day refresh token window
        token_manager.force_refresh()
    except SchwabReauthRequired:
        logger.critical(
            "[schwab_sync] Schwab re-authentication required — "
            "refresh token expired. Sync aborted. Manual browser auth needed."
        )
        return
    except Exception as exc:
        logger.error("[schwab_sync] Token refresh failed: %s", exc)
        return

    try:
        sync_schwab_accounts(token_manager)
    except SchwabReauthRequired:
        logger.critical("[schwab_sync] Schwab re-auth required during account sync.")
        return
    except Exception as exc:
        logger.error("[schwab_sync] Account sync failed: %s", exc)

    try:
        sync_schwab_positions(token_manager)
    except SchwabReauthRequired:
        logger.critical("[schwab_sync] Schwab re-auth required during positions sync.")
        return
    except Exception as exc:
        logger.error("[schwab_sync] Positions sync failed: %s", exc)

    try:
        sync_schwab_orders(token_manager)
    except SchwabReauthRequired:
        logger.critical("[schwab_sync] Schwab re-auth required during orders sync.")
        return
    except Exception as exc:
        logger.error("[schwab_sync] Orders sync failed: %s", exc)

    try:
        sync_schwab_dividend_transactions(token_manager)
    except SchwabReauthRequired:
        logger.critical("[schwab_sync] Schwab re-auth required during dividend sync.")
        return
    except Exception as exc:
        logger.error("[schwab_sync] Dividend transaction sync failed: %s", exc)

    logger.info("[schwab_sync] Sync complete")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _make_client(token_manager: SchwabTokenManager) -> httpx.Client:
    """Create an httpx client with a valid Schwab Bearer token."""
    access_token = token_manager.get_valid_access_token()
    return httpx.Client(
        base_url=SCHWAB_API_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )


def _handle_schwab_error(response: httpx.Response, context: str) -> None:
    """Log and raise on Schwab API errors."""
    if response.status_code == 401:
        raise SchwabReauthRequired(f"401 Unauthorized during {context}")
    if not response.is_success:
        logger.error(
            "[schwab_sync] HTTP %d during %s: %s",
            response.status_code,
            context,
            response.text[:300],
        )
        response.raise_for_status()


# ---------------------------------------------------------------------------
# Account sync (balances)
# ---------------------------------------------------------------------------

def _fetch_account_hashes(token_manager: SchwabTokenManager) -> dict[str, str]:
    """Fetch encrypted account hashes from /accounts/accountNumbers.
    Returns a dict of alias → hashValue for use in sub-endpoints."""
    with _make_client(token_manager) as client:
        response = client.get("/accounts/accountNumbers")
    _handle_schwab_error(response, "/accounts/accountNumbers")

    account_map = _load_account_number_to_alias()
    result: dict[str, str] = {}
    for entry in response.json():
        acct_num = entry.get("accountNumber", "")
        hash_value = entry.get("hashValue", "")
        alias = account_map.get(acct_num)
        if alias and hash_value:
            result[alias] = hash_value
        elif not alias:
            logger.warning(
                "[schwab_sync] Unknown account number %s — add it to SCHWAB_ACCOUNT_MAP env var",
                acct_num,
            )
    return result


def sync_schwab_accounts(token_manager: SchwabTokenManager) -> None:
    """
    Fetch account list from /accounts and /accounts/accountNumbers.
    - Writes balance snapshots (liquidationValue as portfolio_value).
    - Stores alias → accountHash mapping in token file for use by other sync functions.
    """
    # First, get encrypted hashes needed for sub-endpoints
    new_hashes = _fetch_account_hashes(token_manager)
    if new_hashes:
        token_manager.update_account_hashes(new_hashes)

    # Now fetch balances
    with _make_client(token_manager) as client:
        response = client.get("/accounts", params={"fields": "positions"})
    _handle_schwab_error(response, "/accounts")

    accounts_data: list[dict[str, Any]] = response.json()

    for account_data in accounts_data:
        securities_account = account_data.get("securitiesAccount", {})
        account_map = _load_account_number_to_alias()
        acct_num = securities_account.get("accountNumber", "")
        alias = account_map.get(acct_num)
        if not alias:
            logger.warning("[schwab_sync] Skipping unknown account %s", acct_num)
            continue

        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        clean_balance = deidentify_schwab_balance(securities_account, str(account_uuid))

        with get_session() as session:
            # Delete existing balance for this account + date to prevent duplicates on re-run
            session.query(BalanceRow).filter_by(
                account_id=account_uuid,
                balance_date=clean_balance["balance_date"],
                balance_type=clean_balance["balance_type"],
            ).delete()

            row = BalanceRow(id=uuid.uuid4(), **clean_balance)
            session.add(row)

        logger.info(
            "[schwab_sync] Balance snapshot: %r = %.2f (portfolio_value)",
            alias,
            clean_balance["balance_amount"],
        )


# ---------------------------------------------------------------------------
# Positions sync (holdings)
# ---------------------------------------------------------------------------

def sync_schwab_positions(token_manager: SchwabTokenManager) -> None:
    """
    Fetch holdings for each account from /accounts/{accountHash}?fields=positions.
    Writes a Holding row per position for today's snapshot date.
    """
    hashes = token_manager.get_account_hashes()
    if not hashes:
        logger.warning("[schwab_sync] No account hashes available — run account sync first")
        return

    snapshot_date = date.today()

    for alias, account_hash in hashes.items():
        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        with _make_client(token_manager) as client:
            response = client.get(f"/accounts/{account_hash}", params={"fields": "positions"})
        _handle_schwab_error(response, f"/accounts/{alias} positions")

        account_data = response.json()
        positions = account_data.get("securitiesAccount", {}).get("positions", [])

        holdings_written = 0
        with get_session() as session:
            # Delete existing holdings for this account + date to prevent duplicates on re-run
            session.query(HoldingRow).filter_by(
                account_id=account_uuid, snapshot_date=snapshot_date
            ).delete()

            for raw_pos in positions:
                clean = deidentify_schwab_position(raw_pos, str(account_uuid), snapshot_date)
                if clean is None:
                    continue
                row = HoldingRow(id=uuid.uuid4(), **clean)
                session.add(row)
                holdings_written += 1

        logger.info("[schwab_sync] %r — %d positions written for %s", alias, holdings_written, snapshot_date)


# ---------------------------------------------------------------------------
# Orders sync (investment transactions)
# ---------------------------------------------------------------------------

def sync_schwab_orders(token_manager: SchwabTokenManager) -> None:
    """
    Fetch recent filled orders from /accounts/{accountHash}/orders.
    Maps filled orders to investment transactions in the transactions table.
    Only FILLED orders for the last 90 days are processed.
    """
    hashes = token_manager.get_account_hashes()
    if not hashes:
        logger.warning("[schwab_sync] No account hashes available — skipping orders sync")
        return

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=SCHWAB_ORDERS_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    for alias, account_hash in hashes.items():
        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        with _make_client(token_manager) as client:
            response = client.get(
                f"/accounts/{account_hash}/orders",
                params={"fromEnteredTime": from_date, "toEnteredTime": to_date, "status": "FILLED"},
            )
        _handle_schwab_error(response, f"/orders for {alias}")

        orders: list[dict[str, Any]] = response.json()
        txn_count = 0

        with get_session() as session:
            for order in orders:
                txn = _map_order_to_transaction(order, str(account_uuid))
                if txn is None:
                    continue
                row = TransactionRow(id=uuid.uuid4(), **txn)
                session.merge(row)  # use merge for idempotency on Schwab orders (no plaid_transaction_id)
                txn_count += 1

        logger.info("[schwab_sync] %r — %d investment transactions written", alias, txn_count)


def _map_order_to_transaction(order: dict[str, Any], account_uuid: str) -> dict[str, Any] | None:
    """
    Map a Schwab filled order dict to a transactions table row.

    Investment orders have no plaid_transaction_id. We store the ticker symbol
    in merchant_name and set category = 'Investment Transfer'.
    """
    legs = order.get("orderLegCollection", [])
    if not legs:
        return None

    leg = legs[0]
    instrument = leg.get("instrument", {})
    symbol: str | None = instrument.get("symbol")

    order_date_raw = order.get("enteredTime") or order.get("closeTime")
    if order_date_raw:
        try:
            txn_date = datetime.fromisoformat(order_date_raw.replace("Z", "+00:00")).date()
        except ValueError:
            txn_date = date.today()
    else:
        txn_date = date.today()

    price = float(order.get("price") or order.get("filledPrice") or 0.0)
    quantity = float(leg.get("quantity", 0.0))
    amount = price * quantity

    return {
        "account_id": account_uuid,
        "plaid_transaction_id": None,  # Schwab orders have no Plaid ID
        "date": txn_date,
        "amount": amount,
        "merchant_name": symbol[:255] if symbol else "Unknown",
        "category": "Investment Transfer",
        "subcategory": leg.get("instruction", ""),  # BUY / SELL
        "is_pending": False,
        "is_fixed_expense": False,
        "notes": None,
    }


# ---------------------------------------------------------------------------
# Dividend/interest transactions sync (dividend & income calendar — finforge-5)
# ---------------------------------------------------------------------------
#
# The Schwab Trader API's /orders endpoint (used above) only reports BUY/SELL
# order activity — dividend and interest cash activity shows up on the
# separate /accounts/{hash}/transactions endpoint instead, under
# type=DIVIDEND_OR_INTEREST. We store those as their own dividend_transactions
# rows (not the generic `transactions` table) since they carry per-share/DRIP
# metadata that ordinary transactions don't.

DIVIDEND_TRANSACTION_TYPES = {"DIVIDEND_OR_INTEREST", "DIVIDEND", "INTEREST"}
# Non-equity legs (cash movements) that show up alongside the real instrument leg
# in a dividend transaction's transferItems — never treat these as "the symbol".
_NON_EQUITY_ASSET_TYPES = {"CURRENCY", "CASH_EQUIVALENT"}


def sync_schwab_dividend_transactions(token_manager: SchwabTokenManager) -> None:
    """
    Fetch dividend/interest activity from /accounts/{accountHash}/transactions
    and upsert into dividend_transactions. Per-share amount, quantity, and DRIP
    linkage are backfilled separately by cron/dividend_engine.py once the
    matching holdings snapshot and any reinvestment buy exist.
    """
    hashes = token_manager.get_account_hashes()
    if not hashes:
        logger.warning("[schwab_sync] No account hashes available — skipping dividend sync")
        return

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=SCHWAB_DIVIDENDS_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    for alias, account_hash in hashes.items():
        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        try:
            with _make_client(token_manager) as client:
                response = client.get(
                    f"/accounts/{account_hash}/transactions",
                    params={
                        "startDate": from_date,
                        "endDate": to_date,
                        "types": "DIVIDEND_OR_INTEREST",
                    },
                )
            _handle_schwab_error(response, f"/transactions for {alias}")
        except SchwabReauthRequired:
            raise
        except Exception as exc:
            # Some Schwab accounts/endpoints reject the `types` filter shape;
            # log and skip this account rather than aborting the whole sync.
            logger.error("[schwab_sync] Failed to fetch dividend transactions for %r: %s", alias, exc)
            continue

        raw_txns: list[dict[str, Any]] = response.json()
        written = 0

        with get_session() as session:
            for raw in raw_txns:
                mapped = _map_dividend_transaction(raw, str(account_uuid))
                if mapped is None:
                    continue
                if mapped.get("schwab_activity_id"):
                    existing = (
                        session.query(DividendTransactionRow)
                        .filter_by(schwab_activity_id=mapped["schwab_activity_id"])
                        .first()
                    )
                    if existing is not None:
                        continue
                row = DividendTransactionRow(id=uuid.uuid4(), **mapped)
                session.add(row)
                written += 1

        logger.info("[schwab_sync] %r — %d dividend/interest transaction(s) written", alias, written)


def _map_dividend_transaction(txn: dict[str, Any], account_uuid: str) -> dict[str, Any] | None:
    """
    Map a Schwab /transactions entry (type=DIVIDEND_OR_INTEREST) to a
    dividend_transactions row. Returns None for cash-only interest entries
    with no underlying symbol (nothing to project income for) or entries we
    can't confidently parse.
    """
    txn_type = str(txn.get("type") or "").upper()
    if txn_type and txn_type not in DIVIDEND_TRANSACTION_TYPES:
        return None

    transfer_items = txn.get("transferItems") or []
    symbol: str | None = None
    amount: float = 0.0
    found_amount = False

    for item in transfer_items:
        instrument = item.get("instrument") or {}
        asset_type = str(instrument.get("assetType") or "").upper()
        item_symbol = instrument.get("symbol")
        if item_symbol and asset_type not in _NON_EQUITY_ASSET_TYPES:
            symbol = item_symbol
        raw_amount = item.get("amount")
        if raw_amount is not None:
            try:
                amount += float(raw_amount)
                found_amount = True
            except (TypeError, ValueError):
                pass

    if not found_amount:
        net_amount = txn.get("netAmount")
        if net_amount is not None:
            try:
                amount = float(net_amount)
            except (TypeError, ValueError):
                amount = 0.0

    if not symbol:
        # Plain cash interest with no underlying holding — nothing to project.
        return None
    if amount == 0.0:
        return None

    date_raw = txn.get("settlementDate") or txn.get("tradeDate") or txn.get("time")
    if date_raw:
        try:
            pay_date = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00")).date()
        except ValueError:
            pay_date = date.today()
    else:
        pay_date = date.today()

    description = str(txn.get("description") or txn.get("type") or "").upper()
    activity_type = "interest" if "INTEREST" in description and "DIVIDEND" not in description else "dividend"

    activity_id = txn.get("activityId") or txn.get("transactionId") or txn.get("orderId")

    return {
        "account_id": account_uuid,
        "symbol": symbol[:20],
        "pay_date": pay_date,
        "amount": abs(amount),
        "activity_type": activity_type,
        "schwab_activity_id": str(activity_id) if activity_id is not None else None,
    }
