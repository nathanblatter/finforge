"""
Plaid data sync for FinForge.

Syncs transactions and balances for:
  - WF Checking      (checking / Wells Fargo)
  - WF Credit Card   (credit_card / Wells Fargo)
  - Amex Credit Card (credit_card / American Express)

Access tokens are stored in environment variables ONLY — never in the DB.
Cursors for /transactions/sync are persisted in a JSON file on disk.

PRD requirements implemented:
  - /transactions/sync for delta syncs (added/modified/removed)
  - /accounts/balance/get for daily balance snapshots
  - Idempotent upserts via INSERT ... ON CONFLICT (plaid_transaction_id) DO UPDATE
  - ITEM_LOGIN_REQUIRED → ERROR log (DB alert wired in Phase 5)
  - Cursor persistence between runs
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
import plaid

from config import settings
from db import get_session, get_or_create_account
from etl.deidentify import deidentify_plaid_transaction, deidentify_plaid_balance
from integrations.plaid_client import get_plaid_client

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Account config — alias → (account_type, institution)
# ---------------------------------------------------------------------------

ACCOUNT_META: dict[str, tuple[str, str]] = {
    "WF Checking": ("checking", "Wells Fargo"),
    "WF Credit Card": ("credit_card", "Wells Fargo"),
    "Amex Credit Card": ("credit_card", "American Express"),
}

# Env var name for each alias (spaces replaced with underscores, uppercased)
def _access_token_env_key(alias: str) -> str:
    return "PLAID_" + alias.upper().replace(" ", "_") + "_ACCESS_TOKEN"


# Map from FinForge alias to the key used in plaid_tokens.json (institution name lowercased, spaces → _)
_ALIAS_TO_TOKEN_KEY: dict[str, list[str]] = {
    "WF Checking": ["wells_fargo"],
    "WF Credit Card": ["wells_fargo"],
    "Amex Credit Card": ["american_express", "amex"],
}

PLAID_TOKENS_FILE = "/secrets/plaid_tokens.json"


def _load_plaid_tokens_file() -> dict:
    """Load saved tokens from Plaid Link exchange."""
    try:
        with open(PLAID_TOKENS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_access_token(alias: str) -> str | None:
    """
    Get access token for an alias. Checks env vars first,
    then falls back to /secrets/plaid_tokens.json (saved by Plaid Link).
    """
    # Try env var first
    token = os.environ.get(_access_token_env_key(alias))
    if token:
        return token

    # Fall back to tokens file from Plaid Link
    tokens = _load_plaid_tokens_file()
    candidate_keys = _ALIAS_TO_TOKEN_KEY.get(alias, [])
    for key in candidate_keys:
        if key in tokens and tokens[key].get("access_token"):
            return tokens[key]["access_token"]

    return None


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------

CURSOR_FILE = os.environ.get("PLAID_CURSOR_FILE", "/secrets/plaid_cursors.json")


def _load_cursors() -> dict[str, str | None]:
    """Load cursor dict from disk. Returns empty dict if file missing."""
    try:
        with open(CURSOR_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("Could not load cursor file %s: %s", CURSOR_FILE, exc)
        return {}


def _save_cursors(cursors: dict[str, str | None]) -> None:
    """Atomically save cursor dict to disk."""
    tmp = CURSOR_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(CURSOR_FILE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(cursors, f, indent=2)
        os.replace(tmp, CURSOR_FILE)
    except Exception as exc:
        logger.error("Failed to save cursor file: %s", exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Plaid account type → FinForge account type
_PLAID_TYPE_TO_FF: dict[str, str] = {
    "depository": "checking",
    "credit": "credit_card",
}

# Map FinForge alias to Plaid account type for matching
_ALIAS_PLAID_TYPE: dict[str, str] = {
    "WF Checking": "depository",
    "WF Credit Card": "credit",
    "Amex Credit Card": "credit",
}


def _build_plaid_account_map(
    client: Any, access_token: str, aliases: list[str],
) -> dict[str, str]:
    """
    For a Plaid Item, build a mapping of Plaid account_id → FinForge account UUID.
    Fetches account list from Plaid and matches by type to the given aliases.
    """
    from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest as ABR

    resp = client.accounts_balance_get(ABR(access_token=access_token))
    plaid_accounts = resp.accounts or []

    acct_map: dict[str, str] = {}  # plaid_account_id → finforge UUID string

    for plaid_acct in plaid_accounts:
        pa = plaid_acct.to_dict()
        plaid_type = pa.get("type", "")  # "depository", "credit", etc.

        # Find matching FinForge alias
        for alias in aliases:
            expected_plaid_type = _ALIAS_PLAID_TYPE.get(alias)
            if expected_plaid_type == plaid_type:
                account_type, institution = ACCOUNT_META.get(alias, ("checking", "Unknown"))
                with get_session() as session:
                    ff_uuid = get_or_create_account(session, alias, account_type, institution)
                acct_map[pa["account_id"]] = str(ff_uuid)
                break

    return acct_map


def run_plaid_sync() -> None:
    """
    Main entry point for the Plaid sync job (called from cron/main.py).
    Iterates all configured Plaid accounts, syncing transactions and balances.
    Handles multi-account Items (e.g. WF checking + credit card under one token).
    """
    accounts_env = os.environ.get("PLAID_ACCOUNTS", "WF Checking,WF Credit Card,Amex Credit Card")
    aliases = [a.strip() for a in accounts_env.split(",") if a.strip()]

    client = get_plaid_client()
    cursors = _load_cursors()

    # Group aliases by access token so multi-account Items are synced once
    token_to_aliases: dict[str, list[str]] = {}
    for alias in aliases:
        access_token = _get_access_token(alias)
        if not access_token:
            logger.warning("[plaid_sync] No access token for %r — skipping", alias)
            continue
        token_to_aliases.setdefault(access_token, []).append(alias)

    for access_token, group_aliases in token_to_aliases.items():
        # Build Plaid account_id → FinForge UUID mapping
        try:
            acct_map = _build_plaid_account_map(client, access_token, group_aliases)
        except Exception as exc:
            logger.error("[plaid_sync] Failed to build account map for %r: %s", group_aliases, exc)
            continue

        if not acct_map:
            logger.warning("[plaid_sync] No account mapping for %r — skipping", group_aliases)
            continue

        # Use first alias as cursor key for the Item
        cursor_key = group_aliases[0]

        # Sync transactions (once per Item, routing to correct account)
        try:
            new_cursor = sync_transactions(client, access_token, cursor_key, acct_map, cursors)
            cursors[cursor_key] = new_cursor
            # Clear duplicate cursors for other aliases in the group
            for alias in group_aliases[1:]:
                cursors.pop(alias, None)
            _save_cursors(cursors)
        except Exception as exc:
            logger.error("[plaid_sync] Transaction sync failed for %r: %s", group_aliases, exc)

        # Sync balances per alias
        for alias in group_aliases:
            account_type, institution = ACCOUNT_META.get(alias, ("checking", "Unknown"))
            with get_session() as session:
                account_uuid = get_or_create_account(session, alias, account_type, institution)
            try:
                sync_balances(client, access_token, alias, str(account_uuid), account_type)
            except Exception as exc:
                logger.error("[plaid_sync] Balance sync failed for %r: %s", alias, exc)

    logger.info("[plaid_sync] Sync complete for %d accounts", len(aliases))


# ---------------------------------------------------------------------------
# Transaction sync
# ---------------------------------------------------------------------------

def sync_transactions(
    client: Any,
    access_token: str,
    cursor_key: str,
    acct_map: dict[str, str],
    cursors: dict[str, str | None],
) -> str | None:
    """
    Sync transactions for one Plaid Item using /transactions/sync.

    acct_map: Plaid account_id → FinForge UUID string.
    Each transaction is routed to the correct FinForge account based on
    its Plaid account_id.

    Returns the new cursor string to persist for next run.
    """
    from db import TransactionRow
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    cursor = cursors.get(cursor_key)
    added_count = modified_count = removed_count = skipped_count = 0

    has_more = True
    while has_more:
        request = TransactionsSyncRequest(access_token=access_token)
        if cursor:
            request.cursor = cursor

        try:
            response = client.transactions_sync(request)
        except plaid.ApiException as exc:
            body = exc.body if hasattr(exc, "body") else str(exc)
            if "ITEM_LOGIN_REQUIRED" in body or "ITEM_ERROR" in body:
                logger.error(
                    "[plaid_sync] ITEM_LOGIN_REQUIRED for %r — "
                    "re-authentication needed in Plaid Link. Error: %s",
                    cursor_key, body,
                )
            else:
                logger.error("[plaid_sync] Plaid API error for %r: %s", cursor_key, body)
            raise

        added = response.added or []
        modified = response.modified or []
        removed = response.removed or []
        has_more = response.has_more
        cursor = response.next_cursor

        def _upsert_txns(raw_txns: list) -> int:
            count = 0
            with get_session() as session:
                for raw_txn in raw_txns:
                    txn_dict = raw_txn.to_dict()
                    plaid_acct_id = txn_dict.get("account_id", "")
                    ff_uuid = acct_map.get(plaid_acct_id)
                    if not ff_uuid:
                        continue
                    clean = deidentify_plaid_transaction(txn_dict, ff_uuid)
                    if not clean.get("plaid_transaction_id"):
                        continue
                    stmt = pg_insert(TransactionRow).values(
                        id=uuid.uuid4(),
                        **clean,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["plaid_transaction_id"],
                        set_={
                            "account_id": stmt.excluded.account_id,
                            "amount": stmt.excluded.amount,
                            "merchant_name": stmt.excluded.merchant_name,
                            "category": stmt.excluded.category,
                            "subcategory": stmt.excluded.subcategory,
                            "is_pending": stmt.excluded.is_pending,
                            "is_fixed_expense": stmt.excluded.is_fixed_expense,
                            "updated_at": text("now()"),
                        },
                    )
                    session.execute(stmt)
                    count += 1
            return count

        added_count += _upsert_txns(added)
        modified_count += _upsert_txns(modified)

        # Handle removed transactions
        with get_session() as session:
            for removed_txn in removed:
                txn_id = removed_txn.transaction_id if hasattr(removed_txn, "transaction_id") else removed_txn.get("transaction_id")
                if txn_id:
                    session.query(TransactionRow).filter_by(plaid_transaction_id=txn_id).delete()
            removed_count += len(removed)

    logger.info(
        "[plaid_sync] %r — added=%d modified=%d removed=%d",
        cursor_key, added_count, modified_count, removed_count,
    )
    return cursor


# ---------------------------------------------------------------------------
# Balance sync
# ---------------------------------------------------------------------------

def sync_balances(
    client: Any,
    access_token: str,
    account_alias: str,
    account_uuid: str,
    account_type: str,
) -> None:
    """
    Fetch current balances for one Plaid Item using /accounts/balance/get.
    Writes a new Balance row for today's date.
    """
    from db import BalanceRow

    request = AccountsBalanceGetRequest(access_token=access_token)
    try:
        response = client.accounts_balance_get(request)
    except plaid.ApiException as exc:
        body = exc.body if hasattr(exc, "body") else str(exc)
        if "ITEM_LOGIN_REQUIRED" in body or "ITEM_ERROR" in body:
            logger.error(
                "[plaid_sync] ITEM_LOGIN_REQUIRED fetching balance for %r: %s",
                account_alias, body,
            )
        else:
            logger.error("[plaid_sync] Balance fetch failed for %r: %s", account_alias, body)
        raise

    accounts = response.accounts or []
    if not accounts:
        logger.warning("[plaid_sync] No accounts returned for %r balance fetch", account_alias)
        return

    # Match the correct Plaid account to the FinForge alias by type.
    # A single Plaid Item can have multiple accounts (e.g. WF checking + credit card).
    _TYPE_MATCH = {
        "checking": "depository",
        "credit_card": "credit",
    }
    expected_plaid_type = _TYPE_MATCH.get(account_type, account_type)

    raw_account = None
    for acct in accounts:
        acct_dict = acct.to_dict()
        if acct_dict.get("type") == expected_plaid_type:
            raw_account = acct_dict
            break

    if raw_account is None:
        # Fall back to first account if no type match
        raw_account = accounts[0].to_dict()
        logger.warning("[plaid_sync] No type match for %r (expected %s), using first account", account_alias, expected_plaid_type)

    clean = deidentify_plaid_balance(raw_account, account_uuid, account_type)

    with get_session() as session:
        row = BalanceRow(id=uuid.uuid4(), **clean)
        session.add(row)

    logger.info("[plaid_sync] Balance snapshot written for %r: %.2f", account_alias, clean["balance_amount"])
