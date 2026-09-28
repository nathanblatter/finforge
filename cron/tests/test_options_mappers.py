"""Option-contract handling in the Schwab mappers (covered calls etc.).

Fixtures mirror the live shape seen 2026-09-24 for a sold-to-open AAL call:
position → shortQuantity=1, longQuantity=0, averagePrice=0.22, marketValue=-20.5;
activity → TRADE with an OPTION leg (positionEffect OPENING) and fee legs.
"""

import os
import sys
from datetime import date

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.deidentify import deidentify_schwab_position  # noqa: E402
from etl.options import display_symbol, is_option_symbol, parse_occ_symbol  # noqa: E402
from integrations.schwab_sync import _map_activity_to_investment_txn  # noqa: E402

ACCOUNT = "00000000-0000-0000-0000-000000000001"
AAL_CALL = "AAL   261023C0001550"


def test_parse_occ_symbol():
    c = parse_occ_symbol(AAL_CALL)
    assert c is not None
    assert c.underlying == "AAL"
    assert c.expiration == date(2026, 10, 23)
    assert c.put_call == "CALL"
    assert str(c.strike) == "15.50"
    assert display_symbol(AAL_CALL) == "AAL 10/23/26 $15.50 Call"
    assert parse_occ_symbol("AAL") is None
    assert parse_occ_symbol("BRK.B") is None
    assert is_option_symbol("SPY   270115P0045000")
    assert display_symbol("NVDA") == "NVDA"


def test_short_option_position_is_negative_with_premium_basis():
    raw = {
        "shortQuantity": 1.0, "longQuantity": 0.0, "averagePrice": 0.22, "marketValue": -20.5,
        "instrument": {"assetType": "OPTION", "symbol": AAL_CALL, "putCall": "CALL", "underlyingSymbol": "AAL"},
    }
    row = deidentify_schwab_position(raw, ACCOUNT, date(2026, 9, 28))
    assert row is not None
    assert row["asset_type"] == "OPTION"
    assert row["quantity"] == -1.0
    assert row["market_value"] == -20.5
    assert abs(row["cost_basis"] - (-22.0)) < 1e-9  # premium received, x100 multiplier


def test_equity_position_unchanged():
    raw = {"longQuantity": 100.0, "shortQuantity": 0.0, "averagePrice": 14.3984, "marketValue": 1353.0,
           "instrument": {"assetType": "EQUITY", "symbol": "AAL"}}
    row = deidentify_schwab_position(raw, ACCOUNT, date(2026, 9, 28))
    assert row["asset_type"] == "EQUITY"
    assert row["quantity"] == 100.0
    assert abs(row["cost_basis"] - 1439.84) < 1e-6


def _option_leg(qty, price, effect):
    return {
        "instrument": {"assetType": "OPTION", "symbol": AAL_CALL, "putCall": "CALL", "underlyingSymbol": "AAL"},
        "amount": qty, "price": price, "positionEffect": effect,
    }


def _fee_leg(cost):
    return {"instrument": {"assetType": "CURRENCY", "symbol": "CURRENCY_USD"}, "amount": cost, "cost": cost, "feeType": "OPT_REG_FEE"}


def test_sell_to_open_call_maps_as_opening_option_trade():
    act = {
        "activityId": 1, "type": "TRADE", "tradeDate": "2026-09-24T14:00:00+0000", "netAmount": 21.34,
        "description": "", "transferItems": [_option_leg(-1.0, 0.22, "OPENING"), _fee_leg(-0.66)],
    }
    row = _map_activity_to_investment_txn(act, ACCOUNT)
    assert row["txn_type"] == "TRADE"
    assert row["action"] == "SELL"
    assert row["asset_type"] == "OPTION"
    assert row["position_effect"] == "OPENING"
    assert row["symbol"] == AAL_CALL
    assert row["quantity"] == 1.0 and row["price"] == 0.22
    assert row["amount"] == 21.34 and abs(row["fees"] - 0.66) < 1e-9


def test_option_expiration_maps_as_zero_cash_close():
    act = {
        "activityId": 2, "type": "RECEIVE_AND_DELIVER", "tradeDate": "2026-10-24T05:00:00+0000",
        "netAmount": 0.0, "description": "REMOVAL OF OPTION DUE TO EXPIRATION",
        "transferItems": [_option_leg(1.0, None, None)],
    }
    row = _map_activity_to_investment_txn(act, ACCOUNT)
    assert row["txn_type"] == "OPTION_EXPIRATION"
    assert row["action"] == "CLOSE"
    assert row["position_effect"] == "CLOSING"
    assert row["amount"] == 0.0 and row["price"] == 0.0

    act["description"] = "REMOVAL OF OPTION DUE TO ASSIGNMENT"
    assert _map_activity_to_investment_txn(act, ACCOUNT)["txn_type"] == "OPTION_ASSIGNMENT"


def test_receive_and_deliver_for_shares_is_ignored():
    act = {
        "activityId": 3, "type": "RECEIVE_AND_DELIVER", "tradeDate": "2026-10-24T05:00:00+0000",
        "netAmount": 0.0, "description": "JOURNAL",
        "transferItems": [{"instrument": {"assetType": "EQUITY", "symbol": "AAL"}, "amount": 100.0}],
    }
    assert _map_activity_to_investment_txn(act, ACCOUNT) is None
