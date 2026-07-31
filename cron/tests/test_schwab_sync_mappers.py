"""Regression tests for the Schwab /transactions activity mappers
(cron/integrations/schwab_sync.py), using synthetic fixtures that match the
REAL payload shapes observed live on 2026-07-31:

  * TRADE activities: transferItems = several CURRENCY_USD legs (cash/fees)
    plus one EQUITY leg carrying symbol + quantity ("amount") + price.
  * DIVIDEND_OR_INTEREST activities: transferItems = a single CURRENCY_USD
    leg; the security is identified ONLY by the top-level description, which
    is a company NAME from Schwab's activity master ("ORACLE CORP",
    "NIKE INC CLASS CLASS B") — never a ticker. A top-level
    qualifiedDividend flag marks qualified dividends.
  * The activity-master names differ from quote-reference names
    ("CLASS CLASS B" vs "Class B", "INCOME" vs "Inc"), which is what the
    normalizing resolver exists for.

These mappers previously wrote NULL symbols for all dividend rows (so the
dividend_transactions fan-out wrote 0 rows) — see finforge bug fixed in the
same commit as these tests.
"""

import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_KEY", "test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations.schwab_sync import (  # noqa: E402
    _map_activity_to_investment_txn,
    _map_dividend_transaction,
    _normalize_security_name,
    _resolve_symbol,
    _tokens_match,
)

ACCOUNT = "00000000-0000-0000-0000-000000000001"

# Quote-reference descriptions as returned by /marketdata/v1/quotes?fields=reference
NAME_MAP = {
    _normalize_security_name("ORACLE CORP"): "ORCL",
    _normalize_security_name("JPMorgan Nasdaq Equity Premium Inc ETF"): "JEPQ",
    _normalize_security_name("NIKE INC Class B"): "NKE",
    _normalize_security_name("ALPHABET INC A"): "GOOGL",
    _normalize_security_name("ALPHABET INC Class C"): "GOOG",
    _normalize_security_name("BANK OF AMERICA CORP"): "BAC",
    _normalize_security_name("NVIDIA CORP"): "NVDA",
    _normalize_security_name("BROADCOM INC"): "AVGO",
}


def currency_leg(amount, cost=0.0):
    return {
        "instrument": {
            "assetType": "CURRENCY",
            "status": "ACTIVE",
            "symbol": "CURRENCY_USD",
            "description": "USD currency",
            "instrumentId": 1,
            "closingPrice": 0.0,
        },
        "amount": amount,
        "cost": cost,
        "price": 0.0,
    }


def trade_activity(symbol, qty, price, net_amount, fee=0.0):
    """Real TRADE shape: several CURRENCY legs (incl. fee legs) + one EQUITY leg."""
    legs = [currency_leg(net_amount)]
    if fee:
        legs.append({
            "instrument": {"assetType": "CURRENCY", "symbol": "CURRENCY_USD"},
            "amount": fee,
            "cost": fee,
            "price": 0.0,
            "feeType": "SEC_FEE",
        })
    legs.append({
        "instrument": {
            "assetType": "EQUITY",
            "status": "ACTIVE",
            "symbol": symbol,
            "uniformSymbol": symbol,
            "instrumentId": 1648296,
            "closingPrice": price,
            "type": "COMMON_STOCK",
        },
        "amount": qty,
        "cost": net_amount,
        "price": price,
    })
    return {
        "activityId": 126000000001,
        "time": "2026-07-27T15:30:00+0000",
        "accountNumber": "63005559",
        "type": "TRADE",
        "status": "VALID",
        "subAccount": "MARGIN",
        "tradeDate": "2026-07-27T15:30:00+0000",
        "settlementDate": "2026-07-28T04:00:00+0000",
        "netAmount": net_amount,
        "transferItems": legs,
    }


def dividend_activity(description, net_amount, qualified=False, activity_id=126095976447):
    """Real DIVIDEND_OR_INTEREST shape: single CURRENCY leg, name-only description."""
    activity = {
        "activityId": activity_id,
        "time": "2026-07-24T07:48:40+0000",
        "description": description,
        "accountNumber": "63005559",
        "type": "DIVIDEND_OR_INTEREST",
        "status": "VALID",
        "subAccount": "MARGIN",
        "tradeDate": "2026-07-24T04:00:00+0000",
        "settlementDate": "2026-07-24T04:00:00+0000",
        "netAmount": net_amount,
        "transferItems": [currency_leg(net_amount)],
    }
    if qualified:
        activity["qualifiedDividend"] = True
    return activity


# ---------------------------------------------------------------------------
# Name normalization / resolution
# ---------------------------------------------------------------------------

def test_normalize_drops_class_filler_and_repeats():
    assert _normalize_security_name("NIKE INC CLASS CLASS B") == "NIKE INC B"
    assert _normalize_security_name("NIKE INC Class B") == "NIKE INC B"
    assert _normalize_security_name("ALPHABET INC CLASS CLASS A") == "ALPHABET INC A"


def test_tokens_match_prefix_abbreviations():
    a = _normalize_security_name("JPMORGAN NASDAQ EQUITY PREMIUM INCOME ETF")
    b = _normalize_security_name("JPMorgan Nasdaq Equity Premium Inc ETF")
    assert _tokens_match(a, b)


def test_single_letter_share_classes_never_cross_match():
    googl = _normalize_security_name("ALPHABET INC CLASS CLASS A")
    goog_key = _normalize_security_name("ALPHABET INC Class C")
    assert not _tokens_match(googl, goog_key)


def test_resolve_exact_and_fuzzy_and_share_classes():
    assert _resolve_symbol("ORACLE CORP", NAME_MAP) == "ORCL"
    assert _resolve_symbol("JPMORGAN NASDAQ EQUITY PREMIUM INCOME ETF", NAME_MAP) == "JEPQ"
    assert _resolve_symbol("NIKE INC CLASS CLASS B", NAME_MAP) == "NKE"
    assert _resolve_symbol("ALPHABET INC CLASS CLASS A", NAME_MAP) == "GOOGL"
    assert _resolve_symbol("ALPHABET INC CLASS CLASS C", NAME_MAP) == "GOOG"
    assert _resolve_symbol("SOME UNKNOWN COMPANY", NAME_MAP) is None
    assert _resolve_symbol("", NAME_MAP) is None


# ---------------------------------------------------------------------------
# TRADE mapping (regression: engine input for the Tax Center lot engine)
# ---------------------------------------------------------------------------

def test_trade_buy_maps_with_quantity_and_price():
    row = _map_activity_to_investment_txn(trade_activity("NVDA", 1.0, 196.425, -196.43), ACCOUNT)
    assert row is not None
    assert row["txn_type"] == "TRADE"
    assert row["action"] == "BUY"  # negative netAmount = cash out
    assert row["symbol"] == "NVDA"
    assert row["quantity"] == 1.0
    assert row["price"] == 196.425
    assert row["amount"] == -196.43
    assert str(row["trade_date"]) == "2026-07-27"


def test_trade_sell_maps_with_fees():
    row = _map_activity_to_investment_txn(trade_activity("BAC", 7.0, 62.425, 436.97, fee=0.01), ACCOUNT)
    assert row is not None
    assert row["action"] == "SELL"
    assert row["symbol"] == "BAC"
    assert row["quantity"] == 7.0
    assert row["fees"] == 0.01


# ---------------------------------------------------------------------------
# DIVIDEND_OR_INTEREST mapping (regression: NULL-symbol bug)
# ---------------------------------------------------------------------------

def test_dividend_resolves_symbol_from_description():
    act = dividend_activity("ORACLE CORP", 0.5, qualified=True)
    row = _map_activity_to_investment_txn(act, ACCOUNT, NAME_MAP)
    assert row is not None
    assert row["symbol"] == "ORCL"  # was NULL before the resolver existed
    assert row["txn_type"] == "DIVIDEND_QUALIFIED"  # from qualifiedDividend flag
    assert row["amount"] == 0.5
    assert row["action"] is None and row["quantity"] is None


def test_dividend_unqualified_defaults_to_dividend():
    act = dividend_activity("BROADCOM INC", 0.65)
    row = _map_activity_to_investment_txn(act, ACCOUNT, NAME_MAP)
    assert row is not None
    assert row["txn_type"] == "DIVIDEND"
    assert row["symbol"] == "AVGO"


def test_bank_interest_classified_and_kept_symbolless():
    act = dividend_activity("BANK INT 111625-121525 SCHWAB BANK", 0.11)
    row = _map_activity_to_investment_txn(act, ACCOUNT, NAME_MAP)
    assert row is not None
    assert row["txn_type"] == "INTEREST"
    assert row["symbol"] is None  # account-level interest, no ticker


def test_dividend_fanout_row_resolves_symbol():
    act = dividend_activity("NIKE INC CLASS CLASS B", 0.45, qualified=True)
    row = _map_dividend_transaction(act, ACCOUNT, NAME_MAP)
    assert row is not None  # was None before (0 rows written to dividend_transactions)
    assert row["symbol"] == "NKE"
    assert row["activity_type"] == "dividend"
    assert row["amount"] == 0.45
    assert str(row["pay_date"]) == "2026-07-24"
    assert row["schwab_activity_id"] == "126095976447"


def test_dividend_fanout_skips_unresolvable_cash_interest():
    act = dividend_activity("BANK INT 111625-121525 SCHWAB BANK", 0.11)
    assert _map_dividend_transaction(act, ACCOUNT, NAME_MAP) is None


def test_trade_activity_never_becomes_dividend_row():
    act = trade_activity("NVDA", 1.0, 196.425, -196.43)
    assert _map_dividend_transaction(act, ACCOUNT, NAME_MAP) is None
