"""Tax Center — taxable-account tax picture, loss-harvesting, and CSV export.

GET /api/v1/tax/summary       — unrealized G/L, TLH opportunities, est. tax savings, YTD realized activity
GET /api/v1/tax/holdings.csv  — per-holding cost basis & unrealized G/L export (tax prep)
GET /api/v1/tax/lots          — per-lot realized short/long-term gains YTD (FIFO from Schwab activity)
GET /api/v1/tax/estimates     — quarterly estimated-tax tracker with safe-harbor logic
GET /api/v1/tax/form1099      — 1099-B/DIV/INT reconciliation aggregates per symbol
GET /api/v1/tax/form1099.csv  — per-symbol 1099 reconciliation export
GET /api/v1/tax/realized.csv  — realized transactions export (Form 8949 columns, tax prep)

Scope notes:
  * Only the taxable Schwab Brokerage account is considered. The Roth IRA is
    tax-advantaged and is intentionally excluded.
  * Unrealized figures and TLH flags come from the daily PortfolioAnalysis table
    (computed by the portfolio_analysis cron).
  * Realized activity in /summary is derived from synced Schwab orders (category
    'Investment Transfer', subcategory 'SELL'). The orders sync only covers a
    trailing ~90-day window and carries no per-lot cost basis, so realized
    figures are reported as proceeds-only and flagged partial.
  * /lots, /estimates, /form1099 and /realized.csv prefer the richer
    investment_transactions table (Schwab /transactions sync: quantity + price,
    dividends, interest, up to a 1-year window). When that table is empty they
    fall back to the orders-derived rows (proceeds-only, unknown basis).
"""

import csv
import io
import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, extract, func
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db
from models.db_models import (
    Account,
    Holding,
    InvestmentTransaction,
    PortfolioAnalysis,
    Transaction,
)
from schemas.schemas import (
    Form1099Response,
    Form1099SymbolRow,
    QuarterEstimate,
    RealizedActivityItem,
    RealizedLot,
    RealizedLotsResponse,
    RealizedSymbolGroup,
    RealizedTotalsModel,
    TaxEstimateResponse,
    TaxSummaryResponse,
    TLHOpportunity,
)
from services.tax_lots import (
    TERM_LONG,
    TERM_SHORT,
    ClosedLot,
    TradeEvent,
    compute_closed_lots,
    summarize_lots,
)

logger = logging.getLogger("finforge.tax")

router = APIRouter(prefix="/tax", tags=["tax"])

PORTFOLIO_SENTINEL = "__PORTFOLIO__"
TAXABLE_ALIAS = "Schwab Brokerage"
INVESTMENT_CATEGORY = "Investment Transfer"
DEFAULT_MARGINAL_RATE = Decimal("0.30")  # combined fed+state estimate; override via ?marginal_rate=
ZERO = Decimal("0.00")


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _taxable_account(db: Session) -> Account | None:
    return (
        db.query(Account)
        .filter(Account.alias == TAXABLE_ALIAS, Account.is_active.is_(True))
        .first()
    )


def _latest_analysis_rows(db: Session, account_id) -> tuple[date | None, list[PortfolioAnalysis]]:
    latest = (
        db.query(func.max(PortfolioAnalysis.analysis_date))
        .filter(PortfolioAnalysis.account_id == account_id)
        .scalar()
    )
    if latest is None:
        return None, []
    rows = (
        db.query(PortfolioAnalysis)
        .filter(
            PortfolioAnalysis.account_id == account_id,
            PortfolioAnalysis.analysis_date == latest,
            PortfolioAnalysis.symbol != PORTFOLIO_SENTINEL,
        )
        .all()
    )
    return latest, rows


@router.get("/summary", response_model=TaxSummaryResponse)
def get_tax_summary(
    marginal_rate: float = Query(
        float(DEFAULT_MARGINAL_RATE), ge=0.0, le=1.0,
        description="Estimated combined marginal tax rate applied to harvestable losses.",
    ),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> TaxSummaryResponse:
    rate = Decimal(str(marginal_rate))
    tax_year = date.today().year
    account = _taxable_account(db)

    if account is None:
        return TaxSummaryResponse(
            analysis_date=None, tax_year=tax_year, marginal_rate=rate,
            net_unrealized_gl=ZERO, gross_unrealized_gains=ZERO, gross_unrealized_losses=ZERO,
            harvestable_loss=ZERO, est_tax_savings=ZERO, tlh_opportunities=[], wash_sale_warnings=0,
            realized_ytd_proceeds=ZERO, realized_ytd_sells=0, realized_activity=[],
        )

    analysis_date, rows = _latest_analysis_rows(db, account.id)

    gross_gains = ZERO
    gross_losses = ZERO  # positive magnitude
    harvestable_loss = ZERO
    wash_sale_warnings = 0
    opportunities: list[TLHOpportunity] = []

    for r in rows:
        if r.unrealized_gl is None:
            continue
        gl = Decimal(str(r.unrealized_gl))
        if gl > 0:
            gross_gains += gl
        elif gl < 0:
            gross_losses += -gl

        if r.tlh_candidate and gl < 0 and r.cost_basis is not None:
            loss = -gl
            opportunities.append(TLHOpportunity(
                symbol=r.symbol,
                market_value=_q2(Decimal(str(r.market_value or 0))),
                cost_basis=_q2(Decimal(str(r.cost_basis))),
                unrealized_loss=_q2(loss),
                est_tax_benefit=_q2(loss * rate),
                wash_sale_risk=bool(r.wash_sale_risk),
                wash_sale_details=r.wash_sale_details,
            ))
            if r.wash_sale_risk:
                wash_sale_warnings += 1
            else:
                # Only count clean (non-wash-sale) losses toward actionable savings.
                harvestable_loss += loss

    opportunities.sort(key=lambda o: o.unrealized_loss, reverse=True)

    # Realized activity (YTD) from synced SELL orders — proceeds only.
    realized_rows = (
        db.query(
            Transaction.merchant_name.label("symbol"),
            func.sum(Transaction.amount).label("proceeds"),
            func.count(Transaction.id).label("cnt"),
        )
        .filter(
            Transaction.account_id == account.id,
            Transaction.category == INVESTMENT_CATEGORY,
            func.upper(func.coalesce(Transaction.subcategory, "")) == "SELL",
            extract("year", Transaction.date) == tax_year,
        )
        .group_by(Transaction.merchant_name)
        .all()
    )
    realized_activity = [
        RealizedActivityItem(
            symbol=row.symbol or "Unknown",
            proceeds=_q2(Decimal(str(row.proceeds or 0))),
            txn_count=int(row.cnt),
        )
        for row in realized_rows
    ]
    realized_activity.sort(key=lambda a: a.proceeds, reverse=True)
    realized_proceeds = sum((a.proceeds for a in realized_activity), ZERO)
    realized_sells = sum(a.txn_count for a in realized_activity)

    return TaxSummaryResponse(
        analysis_date=analysis_date,
        tax_year=tax_year,
        marginal_rate=rate,
        net_unrealized_gl=_q2(gross_gains - gross_losses),
        gross_unrealized_gains=_q2(gross_gains),
        gross_unrealized_losses=_q2(gross_losses),
        harvestable_loss=_q2(harvestable_loss),
        est_tax_savings=_q2(harvestable_loss * rate),
        tlh_opportunities=opportunities,
        wash_sale_warnings=wash_sale_warnings,
        realized_ytd_proceeds=_q2(realized_proceeds),
        realized_ytd_sells=realized_sells,
        realized_activity=realized_activity,
        realized_is_partial=True,
    )


@router.get("/holdings.csv")
def export_holdings_csv(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> Response:
    """Export the latest taxable-account holdings with cost basis & unrealized G/L."""
    account = _taxable_account(db)
    snapshot_date = None
    holdings: list[Holding] = []
    if account is not None:
        snapshot_date = (
            db.query(func.max(Holding.snapshot_date))
            .filter(Holding.account_id == account.id)
            .scalar()
        )
        if snapshot_date is not None:
            holdings = (
                db.query(Holding)
                .filter(Holding.account_id == account.id, Holding.snapshot_date == snapshot_date)
                .order_by(desc(Holding.market_value))
                .all()
            )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "symbol", "quantity", "cost_basis", "market_value",
        "unrealized_gain_loss", "unrealized_gl_pct", "snapshot_date",
    ])
    for h in holdings:
        mv = Decimal(str(h.market_value))
        cb = Decimal(str(h.cost_basis)) if h.cost_basis is not None else None
        gl = (mv - cb) if cb is not None else None
        gl_pct = (gl / cb * 100) if (gl is not None and cb and cb != 0) else None
        writer.writerow([
            h.symbol,
            f"{Decimal(str(h.quantity)):f}",
            f"{cb:.2f}" if cb is not None else "",
            f"{mv:.2f}",
            f"{gl:.2f}" if gl is not None else "",
            f"{gl_pct:.2f}" if gl_pct is not None else "",
            h.snapshot_date.isoformat(),
        ])

    filename = f"finforge_holdings_{(snapshot_date or date.today()).isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Shared loaders — trade events, closed lots, and investment income
# ---------------------------------------------------------------------------

def _load_trade_events(db: Session, account_id) -> tuple[list[TradeEvent], str, date | None]:
    """
    Load trade events for the lot engine.

    Prefers investment_transactions (quantity + price). Falls back to the
    orders-derived rows in transactions (amount-only → unknown basis).
    Returns (events, source, coverage_start).
    """
    rows = (
        db.query(InvestmentTransaction)
        .filter(
            InvestmentTransaction.account_id == account_id,
            InvestmentTransaction.txn_type == "TRADE",
            InvestmentTransaction.symbol.isnot(None),
        )
        .order_by(InvestmentTransaction.trade_date)
        .all()
    )
    if rows:
        events = [
            TradeEvent(
                symbol=r.symbol,
                trade_date=r.trade_date,
                action=(r.action or "").upper(),
                quantity=Decimal(str(r.quantity)) if r.quantity is not None else None,
                amount=abs(Decimal(str(r.amount))),
                fees=Decimal(str(r.fees or 0)),
            )
            for r in rows
            if (r.action or "").upper() in ("BUY", "SELL")
        ]
        coverage_start = min((e.trade_date for e in events), default=None)
        return events, "schwab_transactions", coverage_start

    legacy = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == account_id,
            Transaction.category == INVESTMENT_CATEGORY,
            func.upper(func.coalesce(Transaction.subcategory, "")).in_(["BUY", "SELL"]),
        )
        .order_by(Transaction.date)
        .all()
    )
    events = [
        TradeEvent(
            symbol=(t.merchant_name or "UNKNOWN"),
            trade_date=t.date,
            action=(t.subcategory or "").upper(),
            quantity=None,  # orders rows carry no quantity → proceeds-only lots
            amount=abs(Decimal(str(t.amount))),
        )
        for t in legacy
    ]
    coverage_start = min((e.trade_date for e in events), default=None)
    return events, "orders_fallback", coverage_start


def _realized_lots(db: Session, account_id, tax_year: int) -> tuple[list[ClosedLot], str, date | None]:
    """FIFO-match the full synced history, then keep lots sold in tax_year."""
    events, source, coverage_start = _load_trade_events(db, account_id)
    lots = compute_closed_lots(events)
    return [l for l in lots if l.sold_date.year == tax_year], source, coverage_start


def _income_ytd(db: Session, account_id, tax_year: int) -> dict[str, dict[str, Decimal]]:
    """
    Dividends/interest for the tax year keyed by symbol ('' for account-level
    interest). Values: {'ordinary': …, 'qualified': …, 'interest': …}.
    """
    rows = (
        db.query(InvestmentTransaction)
        .filter(
            InvestmentTransaction.account_id == account_id,
            InvestmentTransaction.txn_type.in_(["DIVIDEND", "DIVIDEND_QUALIFIED", "INTEREST"]),
            extract("year", InvestmentTransaction.trade_date) == tax_year,
        )
        .all()
    )
    income: dict[str, dict[str, Decimal]] = {}
    for r in rows:
        key = (r.symbol or "").upper()
        bucket = income.setdefault(key, {"ordinary": ZERO, "qualified": ZERO, "interest": ZERO})
        amt = Decimal(str(r.amount))
        if r.txn_type == "INTEREST":
            bucket["interest"] += amt
        elif r.txn_type == "DIVIDEND_QUALIFIED":
            bucket["qualified"] += amt
        else:
            bucket["ordinary"] += amt
    return income


def _totals_model(lots: list[ClosedLot]) -> RealizedTotalsModel:
    t = summarize_lots(lots)
    return RealizedTotalsModel(
        short_term_gain=_q2(t.short_term_gain),
        short_term_loss=_q2(t.short_term_loss),
        long_term_gain=_q2(t.long_term_gain),
        long_term_loss=_q2(t.long_term_loss),
        net_short_term=_q2(t.net_short_term),
        net_long_term=_q2(t.net_long_term),
        net_realized=_q2(t.net_realized),
        proceeds=_q2(t.proceeds),
        basis=_q2(t.basis),
        wash_sale_disallowed=_q2(t.wash_sale_disallowed),
        unknown_basis_proceeds=_q2(t.unknown_basis_proceeds),
        lot_count=t.lot_count,
        unknown_basis_lots=t.unknown_basis_lots,
    )


def _lot_model(lot: ClosedLot) -> RealizedLot:
    return RealizedLot(
        symbol=lot.symbol,
        acquired_date=lot.acquired_date,
        sold_date=lot.sold_date,
        quantity=lot.quantity,
        proceeds=_q2(lot.proceeds),
        basis=_q2(lot.basis) if lot.basis is not None else None,
        gain=_q2(lot.gain) if lot.gain is not None else None,
        term=lot.term,
        wash_sale=lot.wash_sale,
        disallowed_loss=_q2(lot.disallowed_loss),
    )


# ---------------------------------------------------------------------------
# Per-lot realized gains
# ---------------------------------------------------------------------------

@router.get("/lots", response_model=RealizedLotsResponse)
def get_realized_lots(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> RealizedLotsResponse:
    """Per-lot realized short/long-term gains & losses for the current tax year."""
    tax_year = date.today().year
    account = _taxable_account(db)
    if account is None:
        return RealizedLotsResponse(
            tax_year=tax_year, source="none", coverage_start=None,
            totals=_totals_model([]), symbols=[],
        )

    lots, source, coverage_start = _realized_lots(db, account.id, tax_year)

    by_symbol: dict[str, list[ClosedLot]] = {}
    for lot in lots:
        by_symbol.setdefault(lot.symbol, []).append(lot)

    groups: list[RealizedSymbolGroup] = []
    for symbol, sym_lots in by_symbol.items():
        t = summarize_lots(sym_lots)
        has_unknown = t.unknown_basis_lots > 0
        groups.append(RealizedSymbolGroup(
            symbol=symbol,
            lot_count=t.lot_count,
            proceeds=_q2(t.proceeds),
            basis=_q2(t.basis) if not has_unknown else None,
            gain=_q2(t.net_realized) if not has_unknown else None,
            net_short_term=_q2(t.net_short_term),
            net_long_term=_q2(t.net_long_term),
            wash_sale_disallowed=_q2(t.wash_sale_disallowed),
            has_unknown_basis=has_unknown,
            lots=[_lot_model(l) for l in sym_lots],
        ))
    groups.sort(key=lambda g: g.proceeds, reverse=True)

    return RealizedLotsResponse(
        tax_year=tax_year,
        source=source,
        coverage_start=coverage_start,
        totals=_totals_model(lots),
        symbols=groups,
    )


# ---------------------------------------------------------------------------
# Quarterly estimated-tax tracker
# ---------------------------------------------------------------------------

DEFAULT_LTCG_RATE = Decimal("0.15")
HIGH_AGI_THRESHOLD = Decimal("150000")  # 110% safe harbor above this prior-year AGI
HIGH_AGI_THRESHOLD_MFS = Decimal("75000")

_QUARTER_DEFS = [
    ("Q1", "Jan 1 – Mar 31", (4, 15), 0),
    ("Q2", "Apr 1 – May 31", (6, 15), 0),
    ("Q3", "Jun 1 – Aug 31", (9, 15), 0),
    ("Q4", "Sep 1 – Dec 31", (1, 15), 1),  # due Jan 15 of the following year
]


@router.get("/estimates", response_model=TaxEstimateResponse)
def get_tax_estimates(
    prior_year_tax: float = Query(0.0, ge=0.0, description="Total tax liability on last year's return (Form 1040 line 22)."),
    prior_year_agi: float = Query(0.0, ge=0.0, description="Prior-year AGI — determines the 100% vs 110% safe harbor."),
    filing_status: str = Query("single", pattern="^(single|married_joint|married_separate|head_of_household)$"),
    marginal_rate: float = Query(float(DEFAULT_MARGINAL_RATE), ge=0.0, le=1.0, description="Marginal ordinary-income rate (fed+state)."),
    ltcg_rate: float = Query(float(DEFAULT_LTCG_RATE), ge=0.0, le=1.0, description="Long-term capital gains / qualified dividend rate."),
    set_aside: float = Query(0.0, ge=0.0, description="Amount already set aside / paid toward this year's estimated taxes."),
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> TaxEstimateResponse:
    """Quarterly estimated-tax obligations from YTD realized gains + dividends/interest."""
    today = date.today()
    tax_year = today.year
    ord_rate = Decimal(str(marginal_rate))
    cap_rate = Decimal(str(ltcg_rate))
    py_tax = Decimal(str(prior_year_tax))
    py_agi = Decimal(str(prior_year_agi))
    aside = Decimal(str(set_aside))
    notes: list[str] = []

    account = _taxable_account(db)
    net_st = net_lt = ZERO
    ordinary_div = qualified_div = interest = ZERO
    if account is not None:
        lots, source, _cov = _realized_lots(db, account.id, tax_year)
        t = summarize_lots(lots)
        net_st, net_lt = t.net_short_term, t.net_long_term
        if source == "orders_fallback":
            notes.append(
                "Realized gains are proceeds-only (orders fallback, no lot basis) — "
                "gain figures are unavailable until the Schwab transactions sync runs."
            )
        if t.unknown_basis_lots:
            notes.append(
                f"{t.unknown_basis_lots} sold lot(s) predate the synced history; their "
                "gains are excluded from the estimate."
            )
        income = _income_ytd(db, account.id, tax_year)
        for bucket in income.values():
            ordinary_div += bucket["ordinary"]
            qualified_div += bucket["qualified"]
            interest += bucket["interest"]
        if not income:
            notes.append("No dividend/interest activity synced yet for this tax year.")

    # Capital-loss ordering: net ST and LT against each other before taxing.
    taxable_st, taxable_lt = net_st, net_lt
    if taxable_st < 0 and taxable_lt > 0:
        taxable_lt = max(ZERO, taxable_lt + taxable_st)
        taxable_st = ZERO
    elif taxable_lt < 0 and taxable_st > 0:
        taxable_st = max(ZERO, taxable_st + taxable_lt)
        taxable_lt = ZERO
    else:
        taxable_st = max(ZERO, taxable_st)
        taxable_lt = max(ZERO, taxable_lt)

    est_tax_st = taxable_st * ord_rate
    est_tax_lt = taxable_lt * cap_rate
    est_tax_div = qualified_div * cap_rate + ordinary_div * ord_rate
    est_tax_int = interest * ord_rate
    est_total = est_tax_st + est_tax_lt + est_tax_div + est_tax_int

    agi_threshold = HIGH_AGI_THRESHOLD_MFS if filing_status == "married_separate" else HIGH_AGI_THRESHOLD
    sh_pct = Decimal("1.10") if py_agi > agi_threshold else Decimal("1.00")
    sh_prior = py_tax * sh_pct
    sh_current = est_total * Decimal("0.90")

    if py_tax > 0:
        required_annual = min(sh_prior, sh_current)
        if required_annual == sh_prior:
            notes.append(f"Prior-year safe harbor ({int(sh_pct * 100)}% of last year's tax) is the cheaper target.")
        else:
            notes.append("90% of current-year estimated tax is the cheaper safe-harbor target.")
    else:
        required_annual = sh_current
        notes.append(
            "Prior-year tax not configured — using 90% of current-year estimated tax. "
            "Set prior_year_tax in the estimate settings for full safe-harbor logic."
        )
    notes.append(
        "Covers investment income only (realized gains, dividends, interest) — "
        "W-2 withholding and other income are outside FinForge's view."
    )

    quarters: list[QuarterEstimate] = []
    due_next_assigned = False
    for i, (qname, period, (month, day), year_offset) in enumerate(_QUARTER_DEFS):
        due = date(tax_year + year_offset, month, day)
        frac = Decimal(str((i + 1) * 25)) / Decimal("100")
        req_cum = required_annual * frac
        req_q = required_annual * Decimal("0.25")
        if due < today:
            status = "past"
        elif not due_next_assigned:
            status = "due_next"
            due_next_assigned = True
        else:
            status = "upcoming"
        quarters.append(QuarterEstimate(
            quarter=qname, period=period, due_date=due,
            required_cumulative=_q2(req_cum), required_quarter=_q2(req_q), status=status,
        ))

    return TaxEstimateResponse(
        tax_year=tax_year,
        as_of=today,
        filing_status=filing_status,
        marginal_rate=ord_rate,
        ltcg_rate=cap_rate,
        prior_year_tax=_q2(py_tax),
        prior_year_agi=_q2(py_agi),
        safe_harbor_pct=sh_pct,
        ytd_net_short_term=_q2(net_st),
        ytd_net_long_term=_q2(net_lt),
        ytd_ordinary_dividends=_q2(ordinary_div),
        ytd_qualified_dividends=_q2(qualified_div),
        ytd_interest=_q2(interest),
        est_tax_short_term=_q2(est_tax_st),
        est_tax_long_term=_q2(est_tax_lt),
        est_tax_dividends=_q2(est_tax_div),
        est_tax_interest=_q2(est_tax_int),
        est_total_tax=_q2(est_total),
        safe_harbor_prior_year=_q2(sh_prior),
        safe_harbor_current_year=_q2(sh_current),
        required_annual=_q2(required_annual),
        set_aside=_q2(aside),
        remaining=_q2(max(ZERO, required_annual - aside)),
        quarters=quarters,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 1099 reconciliation
# ---------------------------------------------------------------------------

def _build_form1099(db: Session, account_id, tax_year: int) -> Form1099Response:
    lots, source, coverage_start = _realized_lots(db, account_id, tax_year)
    income = _income_ytd(db, account_id, tax_year)

    by_symbol: dict[str, list[ClosedLot]] = {}
    for lot in lots:
        by_symbol.setdefault(lot.symbol, []).append(lot)
    all_symbols = sorted(set(by_symbol) | {s for s in income if s})

    st_proceeds = st_basis = st_gain = ZERO
    lt_proceeds = lt_basis = lt_gain = ZERO
    for lot in lots:
        if lot.basis is None or lot.gain is None:
            continue
        if lot.term == TERM_LONG:
            lt_proceeds += lot.proceeds
            lt_basis += lot.basis
            lt_gain += lot.gain
        elif lot.term == TERM_SHORT:
            st_proceeds += lot.proceeds
            st_basis += lot.basis
            st_gain += lot.gain

    rows: list[Form1099SymbolRow] = []
    for symbol in all_symbols:
        sym_lots = by_symbol.get(symbol, [])
        t = summarize_lots(sym_lots)
        bucket = income.get(symbol, {"ordinary": ZERO, "qualified": ZERO, "interest": ZERO})
        has_unknown = t.unknown_basis_lots > 0
        rows.append(Form1099SymbolRow(
            symbol=symbol,
            lot_count=t.lot_count,
            proceeds=_q2(t.proceeds),
            basis=_q2(t.basis) if not has_unknown else None,
            wash_sale_disallowed=_q2(t.wash_sale_disallowed),
            gain=_q2(t.net_realized) if not has_unknown else None,
            net_short_term=_q2(t.net_short_term),
            net_long_term=_q2(t.net_long_term),
            ordinary_dividends=_q2(bucket["ordinary"]),
            qualified_dividends=_q2(bucket["qualified"]),
            has_unknown_basis=has_unknown,
        ))
    rows.sort(key=lambda r: r.proceeds, reverse=True)

    totals = summarize_lots(lots)
    total_interest = sum((b["interest"] for b in income.values()), ZERO)
    account_interest = income.get("", {}).get("interest", ZERO)

    notes = [
        "Aggregated from synced Schwab activity — reconcile against the broker 1099; "
        "the broker form is authoritative.",
    ]
    if source == "orders_fallback":
        notes.append(
            "Built from the orders fallback (proceeds only, ~90-day window) — basis and "
            "dividend columns will populate once the Schwab transactions sync runs."
        )
    if totals.unknown_basis_lots:
        notes.append(
            f"{totals.unknown_basis_lots} lot(s) have unknown basis (acquired before the "
            "synced window) and are excluded from basis/gain totals."
        )
    if account_interest:
        notes.append("Interest includes account-level credits not tied to a symbol.")
    qualified_total = sum((b["qualified"] for b in income.values()), ZERO)
    if qualified_total == 0 and any(b["ordinary"] for b in income.values()):
        notes.append(
            "Schwab activity data does not always distinguish qualified dividends — "
            "expect the broker 1099-DIV to shift some of box 1a into box 1b."
        )

    return Form1099Response(
        tax_year=tax_year,
        source=source,
        coverage_start=coverage_start,
        total_proceeds=_q2(totals.proceeds),
        total_basis=_q2(totals.basis),
        total_wash_sale_disallowed=_q2(totals.wash_sale_disallowed),
        short_term_proceeds=_q2(st_proceeds),
        short_term_basis=_q2(st_basis),
        short_term_gain=_q2(st_gain),
        long_term_proceeds=_q2(lt_proceeds),
        long_term_basis=_q2(lt_basis),
        long_term_gain=_q2(lt_gain),
        unknown_basis_proceeds=_q2(totals.unknown_basis_proceeds),
        total_ordinary_dividends=_q2(sum((b["ordinary"] for b in income.values()), ZERO)),
        total_qualified_dividends=_q2(qualified_total),
        total_interest=_q2(total_interest),
        symbols=rows,
        notes=notes,
    )


@router.get("/form1099", response_model=Form1099Response)
def get_form1099(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> Form1099Response:
    """What the broker 1099 should report, aggregated from synced activity."""
    tax_year = date.today().year
    account = _taxable_account(db)
    if account is None:
        return Form1099Response(
            tax_year=tax_year, source="none", coverage_start=None,
            total_proceeds=ZERO, total_basis=ZERO, total_wash_sale_disallowed=ZERO,
            short_term_proceeds=ZERO, short_term_basis=ZERO, short_term_gain=ZERO,
            long_term_proceeds=ZERO, long_term_basis=ZERO, long_term_gain=ZERO,
            unknown_basis_proceeds=ZERO, total_ordinary_dividends=ZERO,
            total_qualified_dividends=ZERO, total_interest=ZERO, symbols=[],
            notes=["No taxable account configured."],
        )
    return _build_form1099(db, account.id, tax_year)


@router.get("/form1099.csv")
def export_form1099_csv(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> Response:
    """Per-symbol 1099 reconciliation export."""
    tax_year = date.today().year
    account = _taxable_account(db)
    data = _build_form1099(db, account.id, tax_year) if account else None

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "symbol", "sale_lots", "proceeds", "cost_basis", "wash_sale_disallowed",
        "gain_loss", "short_term_gl", "long_term_gl",
        "ordinary_dividends", "qualified_dividends", "basis_complete",
    ])
    if data:
        for r in data.symbols:
            writer.writerow([
                r.symbol, r.lot_count, f"{r.proceeds:.2f}",
                f"{r.basis:.2f}" if r.basis is not None else "",
                f"{r.wash_sale_disallowed:.2f}",
                f"{r.gain:.2f}" if r.gain is not None else "",
                f"{r.net_short_term:.2f}", f"{r.net_long_term:.2f}",
                f"{r.ordinary_dividends:.2f}", f"{r.qualified_dividends:.2f}",
                "no" if r.has_unknown_basis else "yes",
            ])
        writer.writerow([])
        writer.writerow(["TOTAL", "", f"{data.total_proceeds:.2f}", f"{data.total_basis:.2f}",
                         f"{data.total_wash_sale_disallowed:.2f}", "",
                         f"{data.short_term_gain:.2f}", f"{data.long_term_gain:.2f}",
                         f"{data.total_ordinary_dividends:.2f}",
                         f"{data.total_qualified_dividends:.2f}", ""])
        writer.writerow(["INTEREST_1099INT", "", "", "", "", "", "", "", f"{data.total_interest:.2f}", "", ""])

    filename = f"finforge_1099_reconciliation_{tax_year}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Realized transactions export (Form 8949 columns, tax prep)
# ---------------------------------------------------------------------------

@router.get("/realized.csv")
def export_realized_csv(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
) -> Response:
    """Realized-lot export with the columns tax software expects (Form 8949)."""
    tax_year = date.today().year
    account = _taxable_account(db)
    lots: list[ClosedLot] = []
    if account is not None:
        lots, _source, _cov = _realized_lots(db, account.id, tax_year)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "description", "quantity", "date_acquired", "date_sold",
        "proceeds", "cost_basis", "adjustment_code", "adjustment_amount",
        "gain_loss", "term",
    ])
    for lot in sorted(lots, key=lambda l: (l.sold_date, l.symbol)):
        qty = f"{lot.quantity.normalize():f}" if lot.quantity is not None else ""
        desc = f"{qty} {lot.symbol}".strip() if qty else lot.symbol
        writer.writerow([
            desc,
            qty,
            lot.acquired_date.isoformat() if lot.acquired_date else "UNKNOWN",
            lot.sold_date.isoformat(),
            f"{lot.proceeds:.2f}",
            f"{lot.basis:.2f}" if lot.basis is not None else "",
            "W" if lot.wash_sale else "",
            f"{lot.disallowed_loss:.2f}" if lot.wash_sale else "",
            f"{lot.gain:.2f}" if lot.gain is not None else "",
            {TERM_SHORT: "Short", TERM_LONG: "Long"}.get(lot.term, "Unknown"),
        ])

    filename = f"finforge_realized_{tax_year}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
