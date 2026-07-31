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
    HoldingRow,
    InvestmentTransactionRow,
    TransactionRow,
    get_session,
    get_or_create_account,
)
from etl.deidentify import deidentify_schwab_balance, deidentify_schwab_position
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
SCHWAB_ORDERS_LOOKBACK_DAYS = 90
# /transactions allows at most a 1-year window; use it fully so the Tax Center
# can reconstruct lots and dividends for the whole tax year.
SCHWAB_TXNS_LOOKBACK_DAYS = 364

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
        sync_schwab_transactions(token_manager)
    except SchwabReauthRequired:
        logger.critical("[schwab_sync] Schwab re-auth required during transactions sync.")
        return
    except Exception as exc:
        logger.error("[schwab_sync] Transactions sync failed: %s", exc)

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
# Transactions sync — lot-level trades + dividends/interest (Tax Center)
# ---------------------------------------------------------------------------

# Instrument asset types that represent a security (vs. cash/fee legs).
_SECURITY_ASSET_TYPES = {
    "EQUITY", "ETF", "MUTUAL_FUND", "COLLECTIVE_INVESTMENT",
    "FIXED_INCOME", "OPTION", "INDEX", "PRODUCT",
}


def sync_schwab_transactions(token_manager: SchwabTokenManager) -> None:
    """
    Fetch account activity from /accounts/{accountHash}/transactions and store
    it in investment_transactions.

    Unlike the orders sync (90 days, no per-lot data), this endpoint covers up
    to a 1-year window and carries quantity + price per trade plus dividend and
    interest credits — the raw material for the Tax Center's per-lot realized
    gains, estimated-tax tracker, and 1099 reconciliation.
    """
    hashes = token_manager.get_account_hashes()
    if not hashes:
        logger.warning("[schwab_sync] No account hashes available — skipping transactions sync")
        return

    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=SCHWAB_TXNS_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    for alias, account_hash in hashes.items():
        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        with _make_client(token_manager) as client:
            response = client.get(
                f"/accounts/{account_hash}/transactions",
                params={
                    "startDate": from_date,
                    "endDate": to_date,
                    "types": "TRADE,DIVIDEND_OR_INTEREST",
                },
            )
        _handle_schwab_error(response, f"/transactions for {alias}")

        activities: list[dict[str, Any]] = response.json()
        row_count = 0

        with get_session() as session:
            for activity in activities:
                mapped = _map_activity_to_investment_txn(activity, str(account_uuid))
                if mapped is None:
                    continue
                existing = (
                    session.query(InvestmentTransactionRow)
                    .filter(InvestmentTransactionRow.schwab_activity_id == mapped["schwab_activity_id"])
                    .first()
                )
                if existing is not None:
                    for key, value in mapped.items():
                        setattr(existing, key, value)
                else:
                    session.add(InvestmentTransactionRow(id=uuid.uuid4(), **mapped))
                row_count += 1

        logger.info("[schwab_sync] %r — %d investment activities written", alias, row_count)


def _parse_activity_date(raw: str | None) -> date:
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return date.today()


def _classify_dividend_or_interest(description: str) -> str:
    desc = description.upper()
    if "INTEREST" in desc or "SCHWAB1 INT" in desc or " INT " in f" {desc} ":
        return "INTEREST"
    if "QUALIFIED" in desc:
        return "DIVIDEND_QUALIFIED"
    return "DIVIDEND"


def _map_activity_to_investment_txn(
    activity: dict[str, Any], account_uuid: str
) -> dict[str, Any] | None:
    """
    Map a Schwab /transactions activity to an investment_transactions row.

    TRADE activities carry a security transfer item (quantity + price) plus
    fee legs; DIVIDEND_OR_INTEREST activities are cash-only credits whose
    security is identified via the description or an attached instrument.
    """
    activity_id = activity.get("activityId")
    if activity_id is None:
        return None

    activity_type = (activity.get("type") or "").upper()
    if activity_type not in ("TRADE", "DIVIDEND_OR_INTEREST"):
        return None

    net_amount = float(activity.get("netAmount") or 0.0)
    trade_date = _parse_activity_date(activity.get("tradeDate") or activity.get("time"))
    settlement = activity.get("settlementDate")
    settlement_date = _parse_activity_date(settlement) if settlement else None
    description = activity.get("description") or ""

    transfer_items: list[dict[str, Any]] = activity.get("transferItems", []) or []
    symbol: str | None = None
    quantity: float | None = None
    price: float | None = None
    fees = 0.0

    for item in transfer_items:
        instrument = item.get("instrument") or {}
        asset_type = (instrument.get("assetType") or "").upper()
        if item.get("feeType"):
            fees += abs(float(item.get("cost") or item.get("amount") or 0.0))
        elif asset_type in _SECURITY_ASSET_TYPES:
            symbol = instrument.get("symbol") or symbol
            item_qty = item.get("amount")
            if item_qty is not None:
                quantity = abs(float(item_qty))
            if item.get("price") is not None:
                price = float(item["price"])

    if activity_type == "TRADE":
        if symbol is None:
            return None
        txn_type = "TRADE"
        # Cash out (negative net) = BUY; cash in = SELL.
        action = "BUY" if net_amount < 0 else "SELL"
    else:
        txn_type = _classify_dividend_or_interest(description)
        action = None
        quantity = None
        price = None
        if symbol is None and "~" in description:
            # Some payloads encode the payer as "ORDINARY DIVIDEND~SYMBOL".
            candidate = description.split("~")[-1].strip().upper()
            if candidate and len(candidate) <= 20 and " " not in candidate:
                symbol = candidate

    return {
        "account_id": account_uuid,
        "schwab_activity_id": str(activity_id),
        "txn_type": txn_type,
        "action": action,
        "trade_date": trade_date,
        "settlement_date": settlement_date,
        "symbol": (symbol or None) and symbol[:20],
        "description": description or None,
        "quantity": quantity,
        "price": price,
        "amount": net_amount,
        "fees": fees,
    }
