"""Regression tests for the pure FIFO tax-lot engine (services.tax_lots).

Covers the behavior verified correct in the 2026-08-20 adversarial review:
FIFO matching, partial closes, short/long-term boundary, unknown-basis
sells, aggregate totals, and the single-lot wash-sale flag. The known
multi-lot wash-sale proration defect (finforge-33) is deliberately not
pinned here.
"""

from datetime import date
from decimal import Decimal

from services.tax_lots import (
    TERM_LONG,
    TERM_SHORT,
    TERM_UNKNOWN,
    TradeEvent,
    compute_closed_lots,
    summarize_lots,
)


def _buy(symbol, d, qty, amount, fees="0"):
    return TradeEvent(symbol, d, "BUY", Decimal(qty), Decimal(amount), Decimal(fees))


def _sell(symbol, d, qty, amount, fees="0"):
    return TradeEvent(symbol, d, "SELL", Decimal(qty), Decimal(amount), Decimal(fees))


def test_simple_buy_sell_gain():
    lots = compute_closed_lots([
        _buy("VOO", date(2025, 1, 10), "10", "4000"),
        _sell("VOO", date(2025, 6, 10), "10", "5000"),
    ])
    assert len(lots) == 1
    lot = lots[0]
    assert lot.acquired_date == date(2025, 1, 10)
    assert lot.sold_date == date(2025, 6, 10)
    assert lot.gain == Decimal("1000")
    assert lot.term == TERM_SHORT


def test_fifo_order_and_partial_close():
    lots = compute_closed_lots([
        _buy("VOO", date(2024, 1, 2), "10", "3000"),   # $300/sh
        _buy("VOO", date(2024, 6, 3), "10", "4000"),   # $400/sh
        _sell("VOO", date(2025, 8, 1), "15", "7500"),  # $500/sh
    ])
    assert len(lots) == 2
    first, second = lots
    # oldest lot consumed first
    assert first.acquired_date == date(2024, 1, 2)
    assert first.quantity == Decimal("10")
    assert first.gain == Decimal("2000")  # 5000 proceeds - 3000 basis
    assert second.acquired_date == date(2024, 6, 3)
    assert second.quantity == Decimal("5")
    assert second.gain == Decimal("500")  # 2500 proceeds - 2000 basis


def test_long_term_boundary_is_strictly_more_than_one_year():
    exactly_one_year = compute_closed_lots([
        _buy("SPY", date(2024, 3, 1), "1", "100"),
        _sell("SPY", date(2025, 3, 1), "1", "150"),
    ])[0]
    one_day_more = compute_closed_lots([
        _buy("SPY", date(2024, 3, 1), "1", "100"),
        _sell("SPY", date(2025, 3, 2), "1", "150"),
    ])[0]
    assert exactly_one_year.term == TERM_SHORT
    assert one_day_more.term == TERM_LONG


def test_sell_outrunning_history_closes_with_unknown_basis():
    lots = compute_closed_lots([
        _buy("QQQ", date(2025, 2, 1), "5", "2000"),
        _sell("QQQ", date(2025, 3, 1), "8", "4000"),
    ])
    unknown = [l for l in lots if l.term == TERM_UNKNOWN]
    assert len(unknown) == 1
    assert unknown[0].basis is None and unknown[0].gain is None


def test_summarize_lots_totals():
    lots = compute_closed_lots([
        _buy("VOO", date(2023, 1, 2), "10", "3000"),
        _sell("VOO", date(2025, 1, 10), "10", "5000"),  # long gain 2000
        _buy("ARKK", date(2025, 2, 1), "10", "1000"),
        _sell("ARKK", date(2025, 4, 1), "10", "600"),   # short loss 400
    ])
    totals = summarize_lots(lots)
    assert totals.long_term_gain == Decimal("2000")
    assert totals.short_term_loss == Decimal("400")
    assert totals.net_realized == Decimal("1600")
    assert totals.lot_count == 2


def test_wash_sale_flagged_on_repurchase_within_window():
    lots = compute_closed_lots([
        _buy("ARKK", date(2025, 1, 2), "10", "2000"),
        _sell("ARKK", date(2025, 5, 1), "10", "1000"),  # $1000 loss
        _buy("ARKK", date(2025, 5, 15), "10", "1100"),  # repurchase within 30d
    ])
    loss_lot = lots[0]
    assert loss_lot.wash_sale is True
    assert loss_lot.disallowed_loss == Decimal("1000")


def test_no_wash_sale_outside_window():
    lots = compute_closed_lots([
        _buy("ARKK", date(2025, 1, 2), "10", "2000"),
        _sell("ARKK", date(2025, 5, 1), "10", "1000"),
        _buy("ARKK", date(2025, 7, 1), "10", "1100"),  # 61 days later
    ])
    assert lots[0].wash_sale is False
    assert lots[0].disallowed_loss == Decimal("0")
