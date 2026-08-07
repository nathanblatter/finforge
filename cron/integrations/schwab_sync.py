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
                # Idempotency: Schwab orders carry a stable synthetic key in
                # plaid_transaction_id ("schwab_order:<orderId>"). Update in place
                # if we've seen it, else insert. Without this the old uuid4()+merge
                # re-inserted the entire lookback window as new rows every night,
                # manufacturing "duplicate" stock transactions (finforge-26).
                existing = (
                    session.query(TransactionRow)
                    .filter(TransactionRow.plaid_transaction_id == txn["plaid_transaction_id"])
                    .first()
                )
                if existing is not None:
                    for key, value in txn.items():
                        setattr(existing, key, value)
                else:
                    session.add(TransactionRow(id=uuid.uuid4(), **txn))
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

    # Stable synthetic id so repeated syncs update the same row instead of
    # inserting a fresh uuid every night (finforge-26). Prefer Schwab's orderId;
    # fall back to a composite when it's missing so we still don't duplicate.
    order_id = order.get("orderId")
    if order_id is not None:
        synthetic_id = f"schwab_order:{order_id}"
    else:
        synthetic_id = (
            f"schwab_order:{symbol or 'UNK'}:"
            f"{order.get('enteredTime') or order.get('closeTime') or ''}:"
            f"{leg.get('instruction', '')}:{leg.get('quantity', 0)}"
        )

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
        "plaid_transaction_id": synthetic_id,  # stable dedupe key (finforge-26)
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
# Transactions sync — one /transactions fetch feeding BOTH
#   investment_transactions  (Tax Center: lot-level trades + income)
#   dividend_transactions    (dividend & income calendar — finforge-5)
# ---------------------------------------------------------------------------

# Instrument asset types that represent a security (vs. cash/fee legs).
_SECURITY_ASSET_TYPES = {
    "EQUITY", "ETF", "MUTUAL_FUND", "COLLECTIVE_INVESTMENT",
    "FIXED_INCOME", "OPTION", "INDEX", "PRODUCT",
}

DIVIDEND_TRANSACTION_TYPES = {"DIVIDEND_OR_INTEREST", "DIVIDEND", "INTEREST"}
# Non-equity legs (cash movements) that show up alongside the real instrument leg
# in a dividend transaction's transferItems — never treat these as "the symbol".
_NON_EQUITY_ASSET_TYPES = {"CURRENCY", "CASH_EQUIVALENT"}

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"


# ---------------------------------------------------------------------------
# Security-name → symbol resolution for DIVIDEND_OR_INTEREST activities.
#
# Real payload shape (observed live): dividend/interest activities carry ONLY a
# CURRENCY_USD transfer item — the security is identified by the top-level
# `description`, which is the company NAME from Schwab's activity master
# (e.g. "ORACLE CORP", "NIKE INC CLASS CLASS B"), not a ticker. We resolve it
# against quote reference descriptions for the symbols we know about (traded +
# held). The two masters differ slightly ("CLASS CLASS B" vs "Class B",
# "INCOME" vs "Inc"), hence normalization + per-token prefix matching.
# ---------------------------------------------------------------------------

_NAME_PUNCT = str.maketrans({c: " " for c in ".,&'-/()"})


def _normalize_security_name(name: str) -> str:
    """Uppercase, strip punctuation, drop CLASS filler, collapse repeats."""
    tokens = [t for t in name.upper().translate(_NAME_PUNCT).split() if t != "CLASS"]
    out: list[str] = []
    for t in tokens:
        if not out or out[-1] != t:
            out.append(t)
    return " ".join(out)


def _tokens_match(a: str, b: str) -> bool:
    """Same word count and each token pair equal or prefix of the other
    (handles 'INC' vs 'INCOME'); single-letter tokens must match exactly
    (share classes: 'A' vs 'C')."""
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if len(x) == 1 or len(y) == 1:
            return False
        if not (x.startswith(y) or y.startswith(x)):
            return False
    return True


def _resolve_symbol(description: str, name_map: dict[str, str]) -> str | None:
    """Resolve an activity description (company name) to a ticker."""
    if not description:
        return None
    norm = _normalize_security_name(description)
    if norm in name_map:
        return name_map[norm]
    candidates = {sym for key, sym in name_map.items() if _tokens_match(norm, key)}
    if len(candidates) == 1:
        return candidates.pop()
    return None


def _fetch_symbol_name_map(token_manager: SchwabTokenManager, symbols: set[str]) -> dict[str, str]:
    """Fetch quote reference descriptions for `symbols` and build
    {normalized company name: symbol}. Ambiguous names are dropped."""
    symbols = {s for s in symbols if s and not s.startswith("CURRENCY")}
    if not symbols:
        return {}
    try:
        access_token = token_manager.get_valid_access_token()
        response = httpx.get(
            f"{SCHWAB_MARKETDATA_BASE}/quotes",
            params={"symbols": ",".join(sorted(symbols)), "fields": "reference"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        response.raise_for_status()
        quotes: dict[str, Any] = response.json()
    except Exception as exc:
        logger.error("[schwab_sync] Quote reference lookup failed (%d symbols): %s", len(symbols), exc)
        return {}

    name_map: dict[str, str] = {}
    ambiguous: set[str] = set()
    for symbol, quote in quotes.items():
        desc = (quote.get("reference") or {}).get("description")
        if not desc:
            continue
        key = _normalize_security_name(desc)
        if key in name_map and name_map[key] != symbol:
            ambiguous.add(key)
        else:
            name_map[key] = symbol
    for key in ambiguous:
        logger.warning("[schwab_sync] Ambiguous security name %r — dropped from resolver", key)
        name_map.pop(key, None)
    return name_map


def sync_schwab_transactions(token_manager: SchwabTokenManager) -> None:
    """
    Fetch account activity from /accounts/{accountHash}/transactions once and
    fan it out to both consumers:

      * investment_transactions — trades (quantity + price) plus dividend and
        interest credits; raw material for the Tax Center's per-lot realized
        gains, estimated-tax tracker, and 1099 reconciliation.
      * dividend_transactions — dividend/interest cash activity keyed to a
        symbol; consumed by cron/dividend_engine.py for the income calendar
        (per-share backfill, cadence inference, raise/cut history).

    Schwab caps each request at a 1-year window, so we fetch two consecutive
    windows (~2 years total) — dividends are usually quarterly and the engine
    wants enough history to infer cadence; the extra trade history also
    extends lot-basis coverage.
    """
    hashes = token_manager.get_account_hashes()
    if not hashes:
        logger.warning("[schwab_sync] No account hashes available — skipping transactions sync")
        return

    now = datetime.now(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    windows = [
        ((now - timedelta(days=SCHWAB_TXNS_LOOKBACK_DAYS)).strftime(fmt), now.strftime(fmt)),
        (
            (now - timedelta(days=2 * SCHWAB_TXNS_LOOKBACK_DAYS)).strftime(fmt),
            (now - timedelta(days=SCHWAB_TXNS_LOOKBACK_DAYS)).strftime(fmt),
        ),
    ]

    for alias, account_hash in hashes.items():
        account_type, institution = SCHWAB_ACCOUNTS.get(alias, ("brokerage", "Charles Schwab"))

        with get_session() as session:
            account_uuid = get_or_create_account(session, alias, account_type, institution)

        activities: list[dict[str, Any]] = []
        fetch_failed = False
        for from_date, to_date in windows:
            try:
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
            except SchwabReauthRequired:
                raise
            except Exception as exc:
                # Log and continue — a failed (e.g. empty/older) window shouldn't
                # abort the whole account, let alone the whole sync.
                logger.error(
                    "[schwab_sync] Failed to fetch transactions window %s→%s for %r: %s",
                    from_date, to_date, alias, exc,
                )
                fetch_failed = True
                continue
            activities.extend(response.json())

        if fetch_failed and not activities:
            continue

        # Build the name→symbol resolver for this account's dividend activity:
        # candidate symbols come from trades in this batch plus current holdings.
        candidates: set[str] = set()
        for activity in activities:
            for item in activity.get("transferItems") or []:
                instrument = item.get("instrument") or {}
                if (instrument.get("assetType") or "").upper() in _SECURITY_ASSET_TYPES:
                    sym = instrument.get("symbol")
                    if sym:
                        candidates.add(sym)
        with get_session() as session:
            held = (
                session.query(HoldingRow.symbol)
                .filter(HoldingRow.account_id == account_uuid)
                .distinct()
                .all()
            )
            candidates.update(s for (s,) in held)
        name_map = _fetch_symbol_name_map(token_manager, candidates)

        inv_count = 0
        div_count = 0
        with get_session() as session:
            for activity in activities:
                # investment_transactions (trades + dividends/interest)
                mapped = _map_activity_to_investment_txn(activity, str(account_uuid), name_map)
                if mapped is not None:
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
                    inv_count += 1

                # dividend_transactions (income calendar)
                div_mapped = _map_dividend_transaction(activity, str(account_uuid), name_map)
                if div_mapped is not None:
                    if div_mapped.get("schwab_activity_id"):
                        dup = (
                            session.query(DividendTransactionRow)
                            .filter_by(schwab_activity_id=div_mapped["schwab_activity_id"])
                            .first()
                        )
                        if dup is not None:
                            continue
                    session.add(DividendTransactionRow(id=uuid.uuid4(), **div_mapped))
                    div_count += 1

        logger.info(
            "[schwab_sync] %r — %d investment activities, %d dividend/interest rows written",
            alias, inv_count, div_count,
        )


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
    activity: dict[str, Any], account_uuid: str, name_map: dict[str, str] | None = None
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
        # Real payloads carry an explicit qualifiedDividend flag; fall back to
        # description keywords when absent.
        if activity.get("qualifiedDividend"):
            txn_type = "DIVIDEND_QUALIFIED"
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
        if symbol is None and name_map:
            # Observed live shape: description is the company NAME (no ticker
            # anywhere in the activity) — resolve via quote reference names.
            symbol = _resolve_symbol(description, name_map)

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


def _map_dividend_transaction(
    txn: dict[str, Any], account_uuid: str, name_map: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """
    Map a Schwab /transactions entry (type=DIVIDEND_OR_INTEREST) to a
    dividend_transactions row. Returns None for non-dividend activity, for
    cash-only interest entries with no underlying symbol (nothing to project
    income for), and for entries we can't confidently parse.
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

    if not symbol and name_map:
        # Real dividend activities carry only a CURRENCY leg — the security is
        # named (not tickered) in the description. Resolve name → symbol.
        symbol = _resolve_symbol(str(txn.get("description") or ""), name_map)

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
