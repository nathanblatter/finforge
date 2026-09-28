"""Option contracts: OCC parsing and short-lot (covered call) tax treatment."""

from datetime import date
from decimal import Decimal

from services.options import display_symbol, is_option_symbol, parse_occ_symbol
from services.tax_lots import TERM_SHORT, TERM_UNKNOWN, TradeEvent, compute_closed_lots

AAL_CALL = "AAL   261023C00015500"
D = Decimal


def test_parse_occ_symbol_full_and_truncated():
    for sym in (AAL_CALL, "AAL   261023C0001550"):  # 20-char legacy rows lost a digit
        c = parse_occ_symbol(sym)
        assert c is not None
        assert (c.underlying, c.expiration, c.put_call, c.strike) == ("AAL", date(2026, 10, 23), "CALL", D("15.50"))
    assert display_symbol(AAL_CALL) == "AAL 10/23/26 $15.50 Call"
    assert parse_occ_symbol("AAL") is None and not is_option_symbol("BRK.B")


def _sto(day, qty=1, amount=D("22"), fees=D("0.66"), effect="OPENING"):
    return TradeEvent(AAL_CALL, day, "SELL", D(qty), amount, fees, asset_type="OPTION", position_effect=effect)


def test_sell_to_open_is_not_realized_until_closed():
    lots = compute_closed_lots([_sto(date(2026, 9, 24))])
    assert lots == []


def test_buy_to_close_realizes_premium_minus_cost_short_term():
    events = [
        _sto(date(2026, 9, 24)),
        TradeEvent(AAL_CALL, date(2026, 10, 10), "BUY", D(1), D("5"), D("0.65"), "OPTION", "CLOSING"),
    ]
    (lot,) = compute_closed_lots(events)
    assert lot.short and lot.asset_type == "OPTION"
    assert lot.proceeds == D("21.34")  # 22 - 0.66 fees
    assert lot.basis == D("5.65")
    assert lot.gain == D("15.69")
    assert lot.term == TERM_SHORT
    assert (lot.acquired_date, lot.sold_date) == (date(2026, 9, 24), date(2026, 10, 10))


def test_expiration_realizes_full_premium():
    events = [
        _sto(date(2026, 9, 24)),
        TradeEvent(AAL_CALL, date(2026, 10, 24), "CLOSE", D(1), D(0), D(0), "OPTION", "CLOSING"),
    ]
    (lot,) = compute_closed_lots(events)
    assert lot.gain == D("21.34") and lot.basis == D(0) and lot.short


def test_option_sell_without_effect_infers_short_open():
    # Legacy rows synced before position_effect existed: an option SELL with
    # no long lots must open a short, not become an unknown-basis sale.
    lots = compute_closed_lots([_sto(date(2026, 9, 24), effect=None)])
    assert lots == []


def test_equity_sell_still_outruns_history_as_unknown_basis():
    (lot,) = compute_closed_lots([TradeEvent("AAL", date(2026, 9, 24), "SELL", D(100), D("1500"))])
    assert lot.term == TERM_UNKNOWN and not lot.short


def test_long_option_expiring_worthless_is_a_loss():
    events = [
        TradeEvent(AAL_CALL, date(2026, 9, 1), "BUY", D(1), D("30"), D("0.65"), "OPTION", "OPENING"),
        TradeEvent(AAL_CALL, date(2026, 10, 24), "CLOSE", D(1), D(0), D(0), "OPTION", "CLOSING"),
    ]
    (lot,) = compute_closed_lots(events)
    assert lot.gain == D("-30.65") and not lot.short and lot.term == TERM_SHORT


def test_short_then_long_same_symbol_round_trip():
    events = [
        _sto(date(2026, 9, 24), qty=2, amount=D("44"), fees=D("1.32")),
        TradeEvent(AAL_CALL, date(2026, 10, 1), "BUY", D(1), D("8"), D("0.65"), "OPTION", "CLOSING"),
        TradeEvent(AAL_CALL, date(2026, 10, 24), "CLOSE", D(1), D(0), D(0), "OPTION", "CLOSING"),
    ]
    lots = sorted(compute_closed_lots(events), key=lambda l: l.sold_date)
    assert [l.gain for l in lots] == [D("21.34") - D("8.65"), D("21.34")]
