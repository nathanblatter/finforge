"""
Dividend & income calendar endpoints (finforge-5).

GET /api/v1/dividends/income   — projected forward annual income per holding + portfolio total + yield-on-cost
GET /api/v1/dividends/calendar — predicted upcoming ex-div/pay dates + amounts
GET /api/v1/dividends/history  — raw dividend/interest transaction history (DRIP-annotated)

Income projection prefers the market-data-implied rate (MarketDataCache.dividend_yield,
populated by market_data_sync from Schwab quote fundamentals) when available; otherwise
it's derived purely from dividend transaction history, and the response says which.
"""

import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import DividendTransaction, Holding, MarketDataCache
from schemas.schemas import (
    DividendCalendarPayment,
    DividendCalendarResponse,
    DividendHistoryResponse,
    DividendHoldingProjection,
    DividendIncomeSummaryResponse,
    DividendTransactionItem,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])

ZERO = Decimal("0.00")

# median gap between payments (days) -> (frequency label, payments/year)
_FREQUENCY_BUCKETS: list[tuple[Optional[int], str, int]] = [
    (45, "monthly", 12),
    (135, "quarterly", 4),
    (270, "semiannual", 2),
    (None, "annual", 1),
]


def _infer_frequency(pay_dates: list[date]) -> tuple[Optional[str], Optional[int]]:
    if len(pay_dates) < 2:
        return None, None
    gaps = [(b - a).days for a, b in zip(pay_dates, pay_dates[1:]) if (b - a).days > 0]
    if not gaps:
        return None, None
    median_gap = statistics.median(gaps)
    for max_days, label, per_year in _FREQUENCY_BUCKETS:
        if max_days is None or median_gap <= max_days:
            return label, per_year
    return "annual", 1


def _latest_holdings_by_symbol(db: Session) -> dict[str, dict]:
    """Sum current quantity/cost-basis per symbol across the latest snapshot
    of every account (a holding can span multiple accounts)."""
    result: dict[str, dict] = defaultdict(lambda: {"quantity": ZERO, "cost_basis": ZERO, "has_cost_basis": False})

    # Per-account latest snapshot date (accounts sync on different cadences)
    latest_dates = (
        db.query(Holding.account_id, func.max(Holding.snapshot_date).label("max_date"))
        .group_by(Holding.account_id)
        .all()
    )
    if not latest_dates:
        return result

    for account_id, max_date in latest_dates:
        rows = (
            db.query(Holding)
            .filter(Holding.account_id == account_id, Holding.snapshot_date == max_date)
            .all()
        )
        for h in rows:
            entry = result[h.symbol]
            entry["quantity"] += Decimal(str(h.quantity))
            if h.cost_basis is not None:
                entry["cost_basis"] += Decimal(str(h.cost_basis))
                entry["has_cost_basis"] = True

    return result


@router.get("/income", response_model=DividendIncomeSummaryResponse)
def get_dividend_income(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> DividendIncomeSummaryResponse:
    """Projected forward annual dividend income per holding + portfolio total."""
    today = date.today()
    holdings_by_symbol = _latest_holdings_by_symbol(db)

    div_rows = db.query(DividendTransaction).order_by(DividendTransaction.pay_date).all()
    by_symbol: dict[str, list[DividendTransaction]] = defaultdict(list)
    for r in div_rows:
        by_symbol[r.symbol].append(r)

    market_data = {
        m.symbol: m
        for m in db.query(MarketDataCache).filter(MarketDataCache.symbol.in_(list(holdings_by_symbol.keys()) or ["__none__"])).all()
    }

    holdings: list[DividendHoldingProjection] = []
    has_any_market_data_rates = False

    # Union of symbols we currently hold and symbols with dividend history
    # (a symbol may have been sold; we still show its history in /history but
    # skip it here since projecting forward income for a $0 position is moot).
    for symbol, holding in holdings_by_symbol.items():
        quantity = holding["quantity"]
        if quantity <= 0:
            continue
        cost_basis = holding["cost_basis"] if holding["has_cost_basis"] else None

        payments = sorted(by_symbol.get(symbol, []), key=lambda r: r.pay_date)
        pay_dates = [p.pay_date for p in payments]
        frequency, payments_per_year = _infer_frequency(pay_dates)

        latest = payments[-1] if payments else None
        latest_ps: Optional[Decimal] = None
        if latest is not None and latest.per_share_amount is not None:
            try:
                latest_ps = Decimal(str(latest.per_share_amount))
            except InvalidOperation:
                latest_ps = None

        md = market_data.get(symbol)
        indicated_annual_income: Optional[Decimal] = None
        if md is not None and md.dividend_yield is not None and md.last_price is not None:
            try:
                indicated_ps_annual = Decimal(str(md.dividend_yield)) / Decimal("100") * Decimal(str(md.last_price))
                indicated_annual_income = (indicated_ps_annual * quantity).quantize(Decimal("0.01"))
            except InvalidOperation:
                indicated_annual_income = None

        projected_from_history: Optional[Decimal] = None
        if latest_ps is not None and payments_per_year:
            projected_from_history = (latest_ps * payments_per_year * quantity).quantize(Decimal("0.01"))

        if indicated_annual_income is not None:
            projected = indicated_annual_income
            source = "market_data"
            has_any_market_data_rates = True
        elif projected_from_history is not None:
            projected = projected_from_history
            source = "history"
        else:
            projected = ZERO
            source = "insufficient_data"

        yield_on_cost = None
        if cost_basis and cost_basis > 0:
            yield_on_cost = (projected / cost_basis * 100).quantize(Decimal("0.01"))

        reinvested = sum(
            (Decimal(str(p.amount)) for p in payments if p.is_reinvested), ZERO
        )
        cash_received = sum(
            (Decimal(str(p.amount)) for p in payments if not p.is_reinvested), ZERO
        )

        holdings.append(DividendHoldingProjection(
            symbol=symbol,
            quantity=quantity,
            per_share_amount=latest_ps,
            frequency=frequency,
            payments_per_year=payments_per_year,
            projected_annual_income=projected,
            yield_on_cost_pct=yield_on_cost,
            cost_basis=cost_basis,
            source=source,
            last_payment_date=latest.pay_date if latest else None,
            payment_count=len(payments),
            cumulative_reinvested=reinvested,
            cumulative_cash_received=cash_received,
        ))

    holdings.sort(key=lambda h: h.projected_annual_income, reverse=True)

    portfolio_income = sum((h.projected_annual_income for h in holdings), ZERO)
    portfolio_cost_basis = sum((h.cost_basis for h in holdings if h.cost_basis), ZERO)
    portfolio_yield_on_cost = (
        (portfolio_income / portfolio_cost_basis * 100).quantize(Decimal("0.01"))
        if portfolio_cost_basis > 0 else None
    )
    portfolio_reinvested = sum((h.cumulative_reinvested for h in holdings), ZERO)
    portfolio_cash = sum((h.cumulative_cash_received for h in holdings), ZERO)

    return DividendIncomeSummaryResponse(
        portfolio_projected_annual_income=portfolio_income,
        portfolio_yield_on_cost_pct=portfolio_yield_on_cost,
        portfolio_cumulative_reinvested=portfolio_reinvested,
        portfolio_cumulative_cash_received=portfolio_cash,
        holdings=holdings,
        as_of=today,
        has_any_market_data_rates=has_any_market_data_rates,
    )


@router.get("/calendar", response_model=DividendCalendarResponse)
def get_dividend_calendar(
    months: int = Query(3, ge=1, le=12),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> DividendCalendarResponse:
    """Predicted upcoming ex-div/pay dates + amounts, projected from historical cadence."""
    today = date.today()
    end_date = today + timedelta(days=months * 31)

    holdings_by_symbol = _latest_holdings_by_symbol(db)
    div_rows = db.query(DividendTransaction).order_by(DividendTransaction.pay_date).all()
    by_symbol: dict[str, list[DividendTransaction]] = defaultdict(list)
    for r in div_rows:
        by_symbol[r.symbol].append(r)

    payments: list[DividendCalendarPayment] = []

    for symbol, holding in holdings_by_symbol.items():
        quantity = holding["quantity"]
        if quantity <= 0:
            continue

        history = sorted(by_symbol.get(symbol, []), key=lambda r: r.pay_date)
        if len(history) < 2:
            continue  # can't infer cadence from a single payment

        pay_dates = [h.pay_date for h in history]
        gaps = [(b - a).days for a, b in zip(pay_dates, pay_dates[1:]) if (b - a).days > 0]
        if not gaps:
            continue
        median_gap = statistics.median(gaps)
        gap_days = max(int(round(median_gap)), 1)

        # Consistency of historical cadence -> confidence
        if len(gaps) >= 3:
            spread = (max(gaps) - min(gaps)) / median_gap if median_gap else 1
            confidence = "high" if spread <= 0.25 else "medium"
        else:
            confidence = "medium"

        latest = history[-1]
        try:
            latest_ps = Decimal(str(latest.per_share_amount)) if latest.per_share_amount is not None else None
        except InvalidOperation:
            latest_ps = None
        expected_amount = (latest_ps * quantity).quantize(Decimal("0.01")) if latest_ps is not None else Decimal(str(latest.amount))

        # Roll forward from the last known payment date until we exit the window
        next_date = latest.pay_date + timedelta(days=gap_days)
        guard = 0
        while next_date <= end_date and guard < 24:
            if next_date >= today:
                payments.append(DividendCalendarPayment(
                    symbol=symbol,
                    expected_pay_date=next_date,
                    expected_amount=expected_amount,
                    per_share_amount=latest_ps,
                    quantity=quantity,
                    confidence=confidence,
                ))
            next_date = next_date + timedelta(days=gap_days)
            guard += 1

    payments.sort(key=lambda p: p.expected_pay_date)

    return DividendCalendarResponse(payments=payments, start_date=today, end_date=end_date)


@router.get("/history", response_model=DividendHistoryResponse)
def get_dividend_history(
    symbol: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> DividendHistoryResponse:
    """Raw dividend/interest transaction history, DRIP-annotated, newest first."""
    q = db.query(DividendTransaction)
    if symbol:
        q = q.filter(DividendTransaction.symbol == symbol.upper().strip())
    rows = q.order_by(DividendTransaction.pay_date.desc()).all()
    return DividendHistoryResponse(
        transactions=[DividendTransactionItem.model_validate(r) for r in rows]
    )
