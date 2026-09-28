"""
De-identification and normalization of raw Plaid and Schwab API responses.

CRITICAL POLICY (from PRD):
  - NEVER pass account numbers, card numbers, routing numbers, Plaid access
    tokens, Plaid item IDs, Schwab OAuth tokens, SSNs, or credentials into
    any function that writes to the database.
  - Institution account IDs are replaced by the internal FinForge UUID at
    this layer — the UUID is the only account identifier ever written to DB.
  - The mapping of institution account ID → UUID lives in config/env only.
"""

from __future__ import annotations
from etl.options import ASSET_EQUITY, ASSET_OPTION, OPTION_MULTIPLIER, is_option_symbol

import logging
from datetime import date, datetime
from typing import Any

from etl.categories import map_category
from etl.fixed_expenses import is_fixed_expense

logger = logging.getLogger(__name__)

# Fields from raw Plaid transaction responses that must never reach the DB.
# These contain institution-internal identifiers.
_PLAID_STRIP_FIELDS: frozenset[str] = frozenset(
    [
        "account_id",          # Plaid's internal account identifier
        "account_owner",       # account holder name
        "item_id",             # Plaid item ID
        "access_token",        # should never be in a transaction, but strip anyway
        "routing_number",
        "account_number",
        "mask",                # last 4 — we control whether to store this separately
        "unofficial_currency_code",
        "iso_currency_code",   # keep amount, not currency metadata in transaction
    ]
)


# ---------------------------------------------------------------------------
# Plaid transaction de-identification
# ---------------------------------------------------------------------------

def deidentify_plaid_transaction(raw: dict[str, Any], account_uuid: str) -> dict[str, Any]:
    """
    Strip sensitive fields from a raw Plaid transaction dict and normalize
    to the FinForge transactions table schema.

    Args:
        raw:          Raw transaction dict from Plaid /transactions/sync response.
        account_uuid: Internal FinForge UUID string for this account.

    Returns:
        A clean dict with keys matching the transactions table columns.
        Never contains institution account IDs, card numbers, or credentials.
    """
    # Build category mapping — prefer v2 personal_finance_category, fall back to legacy
    plaid_cats: list[str] | None = raw.get("category")
    pfc: dict | None = raw.get("personal_finance_category")
    finforge_category, finforge_subcategory = map_category(plaid_cats, pfc)

    merchant_name: str | None = (
        raw.get("merchant_name")
        or raw.get("name")
        or raw.get("original_description")
    )
    if merchant_name:
        merchant_name = merchant_name.strip()[:255]

    # Plaid amounts: positive = money leaving account (debit), negative = credit
    amount_raw = raw.get("amount", 0)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        amount = 0.0

    raw_date = raw.get("date") or raw.get("authorized_date")
    txn_date: date = _parse_date(raw_date)

    fixed = is_fixed_expense(merchant_name, amount, finforge_category)

    return {
        "account_id": account_uuid,
        "plaid_transaction_id": raw.get("transaction_id"),
        "date": txn_date,
        "amount": amount,
        "merchant_name": merchant_name,
        "category": finforge_category,
        "subcategory": finforge_subcategory,
        "is_pending": bool(raw.get("pending", False)),
        "is_fixed_expense": fixed,
        "notes": None,
    }


# ---------------------------------------------------------------------------
# Plaid balance de-identification
# ---------------------------------------------------------------------------

def deidentify_plaid_balance(raw: dict[str, Any], account_uuid: str, account_type: str) -> dict[str, Any]:
    """
    Extract balance info from a single account entry in a Plaid
    /accounts/balance/get response.

    Args:
        raw:          A single account dict from the Plaid accounts list.
        account_uuid: Internal FinForge UUID string for this account.
        account_type: FinForge account type ('checking', 'credit_card', etc.)

    Returns:
        A clean dict with keys matching the balances table columns.
    """
    balances = raw.get("balances", {})

    # For checking/credit: use current balance
    # For brokerage/IRA: liquidation value preferred, fall back to current
    current = balances.get("current")
    available = balances.get("available")

    balance_amount = current if current is not None else (available or 0.0)
    balance_type = "portfolio_value" if account_type in ("brokerage", "ira") else "cash"

    return {
        "account_id": account_uuid,
        "balance_date": date.today(),
        "balance_amount": float(balance_amount),
        "balance_type": balance_type,
    }


# ---------------------------------------------------------------------------
# Schwab balance de-identification
# ---------------------------------------------------------------------------

def deidentify_schwab_balance(raw: dict[str, Any], account_uuid: str) -> dict[str, Any]:
    """
    Extract balance from a single Schwab account dict returned by /accounts.

    Schwab returns currentBalances.liquidationValue as the total portfolio value
    for brokerage and IRA accounts.

    Args:
        raw:          A single account dict from Schwab /accounts response.
        account_uuid: Internal FinForge UUID string for this account.

    Returns:
        A clean dict with keys matching the balances table columns.
    """
    current_balances = raw.get("currentBalances", {})
    liquidation_value = current_balances.get("liquidationValue")
    cash_balance = current_balances.get("cashBalance", 0.0)

    balance_amount = float(liquidation_value) if liquidation_value is not None else float(cash_balance)

    return {
        "account_id": account_uuid,
        "balance_date": date.today(),
        "balance_amount": balance_amount,
        "balance_type": "portfolio_value",
    }


# ---------------------------------------------------------------------------
# Schwab position de-identification
# ---------------------------------------------------------------------------

def deidentify_schwab_position(
    raw: dict[str, Any],
    account_uuid: str,
    snapshot_date: date,
) -> dict[str, Any] | None:
    """
    Extract holding info from a single Schwab position dict.

    Args:
        raw:           A single position dict from Schwab /positions response.
        account_uuid:  Internal FinForge UUID string for this account.
        snapshot_date: The date to stamp on this snapshot.

    Returns:
        A clean dict with keys matching the holdings table columns,
        or None if the position cannot be parsed (e.g. cash sweep).
    """
    instrument = raw.get("instrument", {})
    symbol: str | None = instrument.get("symbol")

    if not symbol:
        # Skip cash positions or unrecognized instruments
        logger.debug("Skipping position with no symbol: %r", instrument.get("assetType"))
        return None

    asset_type = str(instrument.get("assetType") or "").upper() or ASSET_EQUITY
    if asset_type != ASSET_OPTION and is_option_symbol(symbol):
        asset_type = ASSET_OPTION

    # Schwab reports long and short legs separately; a written (sold-to-open)
    # option shows up as shortQuantity with longQuantity 0. Store a signed
    # quantity so a covered call is -1, not 0.
    long_quantity = _to_float(raw.get("longQuantity")) or 0.0
    short_quantity = _to_float(raw.get("shortQuantity")) or 0.0
    quantity = long_quantity - short_quantity
    market_value = _to_float(raw.get("marketValue")) or 0.0
    average_price = _to_float(raw.get("averagePrice"))

    # Signed net cost: positive = cash paid, negative = premium received.
    # Options quote per share, so scale by the contract multiplier.
    cost_basis: float | None = None
    if average_price is not None:
        multiplier = OPTION_MULTIPLIER if asset_type == ASSET_OPTION else 1
        cost_basis = average_price * quantity * multiplier

    return {
        "account_id": account_uuid,
        "snapshot_date": snapshot_date,
        "symbol": symbol[:32],
        "asset_type": asset_type[:20],
        "quantity": quantity,
        "market_value": market_value,
        "cost_basis": cost_basis,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date:
    """Parse a Plaid date string (YYYY-MM-DD) to a Python date. Defaults to today."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()
