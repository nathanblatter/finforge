"""Tax-lot engine — FIFO lot matching, realized gain/loss, and wash-sale flags.

Consumes trade events from investment_transactions (Schwab /transactions sync,
which carries quantity + price) and produces closed lots: acquired date, sold
date, proceeds, basis, gain, and short/long term. Sells that outrun the synced
buy history close with an unknown basis rather than a wrong one.

Wash-sale detection follows the same convention as the portfolio_analysis cron:
a 30-day replacement window around the loss sale (here: any other BUY of the
same symbol within +/-30 days of the sale date). Disallowed loss is prorated by
replacement quantity — a heuristic, not a per-share IRS matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

WASH_SALE_WINDOW_DAYS = 30  # matches cron/integrations/portfolio_analysis.py
ZERO = Decimal("0")

TERM_SHORT = "short"
TERM_LONG = "long"
TERM_UNKNOWN = "unknown"


@dataclass
class TradeEvent:
    """A single buy or sell of one symbol."""

    symbol: str
    trade_date: date
    action: str  # "BUY" | "SELL"
    quantity: Decimal | None  # None → amount-only event (orders fallback)
    amount: Decimal  # absolute cash amount of the trade (always >= 0)
    fees: Decimal = ZERO


@dataclass
class ClosedLot:
    """A (portion of a) tax lot closed by a sell."""

    symbol: str
    acquired_date: date | None  # None → basis unknown (buy predates synced history)
    sold_date: date
    quantity: Decimal | None
    proceeds: Decimal
    basis: Decimal | None
    gain: Decimal | None  # proceeds - basis, None when basis unknown
    term: str  # TERM_SHORT | TERM_LONG | TERM_UNKNOWN
    wash_sale: bool = False
    disallowed_loss: Decimal = ZERO  # positive magnitude


@dataclass
class _OpenLot:
    acquired_date: date
    remaining_qty: Decimal
    basis_per_share: Decimal


@dataclass
class RealizedTotals:
    """Aggregate realized picture across a set of closed lots."""

    short_term_gain: Decimal = ZERO
    short_term_loss: Decimal = ZERO  # positive magnitude
    long_term_gain: Decimal = ZERO
    long_term_loss: Decimal = ZERO  # positive magnitude
    proceeds: Decimal = ZERO
    basis: Decimal = ZERO  # only lots with known basis
    wash_sale_disallowed: Decimal = ZERO
    unknown_basis_proceeds: Decimal = ZERO
    lot_count: int = 0
    unknown_basis_lots: int = 0

    @property
    def net_short_term(self) -> Decimal:
        return self.short_term_gain - self.short_term_loss

    @property
    def net_long_term(self) -> Decimal:
        return self.long_term_gain - self.long_term_loss

    @property
    def net_realized(self) -> Decimal:
        return self.net_short_term + self.net_long_term


def _is_long_term(acquired: date, sold: date) -> bool:
    """IRS long-term = held MORE than one year (sold after the 1-yr anniversary)."""
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:  # Feb 29 acquisition
        anniversary = acquired.replace(year=acquired.year + 1, day=28)
    return sold > anniversary


def compute_closed_lots(events: list[TradeEvent]) -> list[ClosedLot]:
    """
    FIFO-match sells against buys per symbol and return closed lots.

    Events with quantity=None (legacy orders fallback) can't be lot-matched:
    BUYs are ignored, SELLs become proceeds-only lots with unknown basis/term.
    Fees are folded in: buy fees increase basis, sell fees reduce proceeds.
    """
    by_symbol: dict[str, list[TradeEvent]] = {}
    for ev in events:
        by_symbol.setdefault(ev.symbol.upper(), []).append(ev)

    closed: list[ClosedLot] = []

    for symbol, sym_events in by_symbol.items():
        sym_events.sort(key=lambda e: (e.trade_date, 0 if e.action == "BUY" else 1))
        open_lots: list[_OpenLot] = []

        for ev in sym_events:
            if ev.action == "BUY":
                if ev.quantity is None or ev.quantity <= 0:
                    continue
                basis_total = ev.amount + ev.fees
                open_lots.append(_OpenLot(
                    acquired_date=ev.trade_date,
                    remaining_qty=ev.quantity,
                    basis_per_share=basis_total / ev.quantity,
                ))
                continue

            if ev.action != "SELL":
                continue

            net_proceeds = ev.amount - ev.fees
            if ev.quantity is None or ev.quantity <= 0:
                closed.append(ClosedLot(
                    symbol=symbol, acquired_date=None, sold_date=ev.trade_date,
                    quantity=None, proceeds=net_proceeds, basis=None, gain=None,
                    term=TERM_UNKNOWN,
                ))
                continue

            proceeds_per_share = net_proceeds / ev.quantity
            to_close = ev.quantity

            while to_close > 0 and open_lots:
                lot = open_lots[0]
                take = min(to_close, lot.remaining_qty)
                basis = lot.basis_per_share * take
                proceeds = proceeds_per_share * take
                closed.append(ClosedLot(
                    symbol=symbol,
                    acquired_date=lot.acquired_date,
                    sold_date=ev.trade_date,
                    quantity=take,
                    proceeds=proceeds,
                    basis=basis,
                    gain=proceeds - basis,
                    term=TERM_LONG if _is_long_term(lot.acquired_date, ev.trade_date) else TERM_SHORT,
                ))
                lot.remaining_qty -= take
                to_close -= take
                if lot.remaining_qty <= 0:
                    open_lots.pop(0)

            if to_close > 0:
                # Sold shares acquired before the synced history window.
                closed.append(ClosedLot(
                    symbol=symbol, acquired_date=None, sold_date=ev.trade_date,
                    quantity=to_close, proceeds=proceeds_per_share * to_close,
                    basis=None, gain=None, term=TERM_UNKNOWN,
                ))

        _flag_wash_sales(symbol, sym_events, [c for c in closed if c.symbol == symbol])

    closed.sort(key=lambda c: (c.sold_date, c.symbol), reverse=True)
    return closed


def _flag_wash_sales(symbol: str, events: list[TradeEvent], lots: list[ClosedLot]) -> None:
    """
    Flag loss lots with a replacement BUY within +/-30 days of the sale
    (excluding the buy that opened the lot itself). Disallowed loss is
    prorated by matched replacement quantity vs. lot quantity, and each
    replacement share is consumed by at most one loss lot (earliest sale
    first) so overlapping windows can't disallow the same shares twice.
    Still a heuristic, not per-share IRS matching.
    """
    buys = [e for e in events if e.action == "BUY" and e.quantity is not None and e.quantity > 0]
    if not buys:
        return
    remaining = [b.quantity for b in buys]

    loss_lots = [l for l in lots if l.gain is not None and l.gain < 0]
    loss_lots.sort(key=lambda l: (l.sold_date, l.acquired_date or l.sold_date))

    for lot in loss_lots:
        loss = -lot.gain

        def _in_window(buy: TradeEvent) -> bool:
            if buy.trade_date == lot.acquired_date:
                return False  # the acquisition that created this lot, not a replacement
            return abs((buy.trade_date - lot.sold_date).days) <= WASH_SALE_WINDOW_DAYS

        if not lot.quantity or lot.quantity <= 0:
            # Amount-only lot (no share count): flag fully if any unconsumed
            # in-window replacement exists, without consuming shares.
            if any(remaining[i] > 0 and _in_window(b) for i, b in enumerate(buys)):
                lot.wash_sale = True
                lot.disallowed_loss = loss
            continue

        matched = ZERO
        for i, buy in enumerate(buys):
            if matched >= lot.quantity:
                break
            if remaining[i] <= 0 or not _in_window(buy):
                continue
            take = min(remaining[i], lot.quantity - matched)
            remaining[i] -= take
            matched += take

        if matched > 0:
            lot.wash_sale = True
            lot.disallowed_loss = loss * (matched / lot.quantity)


def summarize_lots(lots: list[ClosedLot]) -> RealizedTotals:
    """Aggregate closed lots into short/long-term gain/loss totals."""
    totals = RealizedTotals()
    for lot in lots:
        totals.lot_count += 1
        totals.proceeds += lot.proceeds
        if lot.basis is None or lot.gain is None:
            totals.unknown_basis_lots += 1
            totals.unknown_basis_proceeds += lot.proceeds
            continue
        totals.basis += lot.basis
        totals.wash_sale_disallowed += lot.disallowed_loss
        if lot.term == TERM_LONG:
            if lot.gain >= 0:
                totals.long_term_gain += lot.gain
            else:
                totals.long_term_loss += -lot.gain
        else:
            if lot.gain >= 0:
                totals.short_term_gain += lot.gain
            else:
                totals.short_term_loss += -lot.gain
    return totals
