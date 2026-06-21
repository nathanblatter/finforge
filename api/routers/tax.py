"""Tax Center — taxable-account tax picture, loss-harvesting, and CSV export.

GET /api/v1/tax/summary       — unrealized G/L, TLH opportunities, est. tax savings, YTD realized activity
GET /api/v1/tax/holdings.csv  — per-holding cost basis & unrealized G/L export (tax prep)

Scope notes:
  * Only the taxable Schwab Brokerage account is considered. The Roth IRA is
    tax-advantaged and is intentionally excluded.
  * Unrealized figures and TLH flags come from the daily PortfolioAnalysis table
    (computed by the portfolio_analysis cron).
  * Realized activity is derived from synced Schwab orders (category
    'Investment Transfer', subcategory 'SELL'). The orders sync only covers a
    trailing ~90-day window and carries no per-lot cost basis, so realized
    figures are reported as proceeds-only and flagged partial.
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
from models.db_models import Account, Holding, PortfolioAnalysis, Transaction
from schemas.schemas import (
    RealizedActivityItem,
    TaxSummaryResponse,
    TLHOpportunity,
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
