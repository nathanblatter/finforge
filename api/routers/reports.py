"""
PDF report generation endpoints for FinForge.

Provides three report families:
  - Financial reports  (net worth, spending, balances)
  - Tithing reports    (income review, 10% computation)
  - Contribution reports (Schwab transfers, Roth IRA headroom)

Each family exposes preview / generate / email endpoints.
"""

from __future__ import annotations

import calendar
import io
import logging
import smtplib
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from email.message import EmailMessage
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func as sqla_func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance, Holding, Transaction
from services.pdf_builder import FinForgePDFBuilder
from services import chart_builder

logger = logging.getLogger("finforge.reports")

router = APIRouter(prefix="/reports", tags=["reports"])

# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    period: str  # "monthly", "quarterly", "annual", "custom"
    month: str = ""  # YYYY-MM
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class TithingRequest(ReportRequest):
    included_transaction_ids: list[str] = []
    in_kind_donations: list[dict] = []  # [{symbol, shares, fair_market_value}]


class ContributionRequest(ReportRequest):
    pass


# ---------------------------------------------------------------------------
# Period resolution
# ---------------------------------------------------------------------------

def _resolve_period(
    period: str,
    month: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> tuple[date, date]:
    """
    Convert a period descriptor into concrete (start_date, end_date).

    - ``monthly``   -> first and last day of *month* (YYYY-MM).
    - ``quarterly`` -> Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec,
                       derived from *month*.
    - ``annual``    -> Jan 1 - Dec 31 of the year in *month*.
    - ``custom``    -> uses *start_date* / *end_date* directly.
    """
    if period == "custom":
        if not start_date or not end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date and end_date are required for custom periods.",
            )
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be on or before end_date.",
            )
        return start_date, end_date

    # All other period types require a valid YYYY-MM month string.
    year, mon = _parse_month(month)

    if period == "monthly":
        first = date(year, mon, 1)
        last_day = calendar.monthrange(year, mon)[1]
        return first, date(year, mon, last_day)

    if period == "quarterly":
        quarter_start_month = ((mon - 1) // 3) * 3 + 1
        q_start = date(year, quarter_start_month, 1)
        q_end_month = quarter_start_month + 2
        last_day = calendar.monthrange(year, q_end_month)[1]
        return q_start, date(year, q_end_month, last_day)

    if period == "annual":
        return date(year, 1, 1), date(year, 12, 31)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unknown period '{period}'. Use monthly, quarterly, annual, or custom.",
    )


def _parse_month(month: str) -> tuple[int, int]:
    """Parse a YYYY-MM string and return (year, month)."""
    try:
        parts = month.split("-")
        year, mon = int(parts[0]), int(parts[1])
        if not (1 <= mon <= 12):
            raise ValueError
        return year, mon
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format '{month}'. Expected YYYY-MM.",
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SMTP_HOST = "docker-services-postfix-1"
_SMTP_PORT = 25
_FROM_ADDR = "noreply@nathanblatter.com"
_TO_ADDR = "nathan.blatter@yahoo.com"

_CREDIT_CARD_ALIASES = {"WF Credit Card", "Amex Credit Card"}
_CHECKING_ALIASES = {"WF Checking"}
_SCHWAB_ALIASES = {"Schwab Brokerage", "Schwab Roth IRA"}
_ROTH_IRA_ALIAS = "Schwab Roth IRA"
_ROTH_ANNUAL_LIMIT = Decimal("7000")


def _email_pdf(buf: io.BytesIO, filename: str, subject: str, body_text: str) -> None:
    """Send a PDF attachment via the local Postfix relay."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _FROM_ADDR
    msg["To"] = _TO_ADDR
    msg.set_content(body_text)
    msg.add_attachment(
        buf.getvalue(),
        maintype="application",
        subtype="pdf",
        filename=filename,
    )
    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(msg)
    except Exception as exc:
        logger.error("Failed to send report email: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email delivery failed: {exc}",
        )


def _currency(value: Decimal | float) -> str:
    """Format a number as a USD string."""
    return f"${float(value):,.2f}"


def _get_latest_balances(
    db: Session,
    end_date: date,
) -> list[tuple[Account, Balance]]:
    """
    Return the most recent Balance snapshot for each active account
    on or before *end_date*.
    """
    accounts = db.query(Account).filter(Account.is_active == True).all()
    results: list[tuple[Account, Balance]] = []
    for acct in accounts:
        bal = (
            db.query(Balance)
            .filter(
                Balance.account_id == acct.id,
                Balance.balance_date <= end_date,
            )
            .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
            .first()
        )
        if bal:
            results.append((acct, bal))
    return results


def _compute_net_worth(pairs: list[tuple[Account, Balance]]) -> dict:
    """
    Derive net_worth, liquid_cash, savings, and cc_debt from account balances.

    Credit-card balances are subtracted (debt); everything else is added.
    """
    liquid_cash = Decimal("0")
    savings = Decimal("0")
    cc_debt = Decimal("0")
    total = Decimal("0")

    for acct, bal in pairs:
        amt = bal.balance_amount
        if acct.account_type == "credit_card":
            cc_debt += amt
            total -= amt
        else:
            total += amt
            if acct.account_type == "checking":
                liquid_cash += amt
            elif acct.account_type in ("brokerage", "ira"):
                savings += amt

    return {
        "net_worth": total,
        "liquid_cash": liquid_cash,
        "savings": savings,
        "cc_debt": cc_debt,
    }


def _spending_by_category(
    db: Session,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Return spending grouped by category (amount > 0, not pending) within period.
    """
    rows = (
        db.query(
            Transaction.category,
            sqla_func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.amount > 0,
            Transaction.is_pending == False,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .group_by(Transaction.category)
        .order_by(sqla_func.sum(Transaction.amount).desc())
        .all()
    )
    return [
        {"category": cat or "Other", "amount": float(total)}
        for cat, total in rows
    ]


def _income_transactions(
    db: Session,
    start_date: date,
    end_date: date,
) -> list[Transaction]:
    """Return income transactions (amount < 0) in period."""
    return (
        db.query(Transaction)
        .filter(
            Transaction.amount < 0,
            Transaction.is_pending == False,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .order_by(Transaction.date)
        .all()
    )


def _period_label(start: date, end: date) -> str:
    """Human-readable label for the report period."""
    if start.month == end.month and start.year == end.year:
        return start.strftime("%B %Y")
    return f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"


def _months_in_range(start: date, end: date) -> list[tuple[date, date]]:
    """Yield (month_start, month_end) pairs for every month touched by range."""
    months: list[tuple[date, date]] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, last_day)
        months.append((current, min(month_end, end)))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def _is_multi_month(start: date, end: date) -> bool:
    return (start.year, start.month) != (end.year, end.month)


# ═══════════════════════════════════════════════════════════════════════════
# FINANCIAL REPORTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/financial/preview")
def financial_preview(
    period: str = Query(default="monthly"),
    month: str = Query(default=""),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    JSON preview of the financial report data for the given period.
    """
    if not month and period != "custom":
        month = date.today().strftime("%Y-%m")

    p_start, p_end = _resolve_period(period, month, start_date, end_date)

    bal_pairs = _get_latest_balances(db, p_end)
    nw = _compute_net_worth(bal_pairs)

    spending = _spending_by_category(db, p_start, p_end)

    account_balances = [
        {"alias": acct.alias, "balance": float(bal.balance_amount)}
        for acct, bal in sorted(bal_pairs, key=lambda p: p[0].alias)
    ]

    return {
        "period": period,
        "start_date": p_start.isoformat(),
        "end_date": p_end.isoformat(),
        "net_worth": float(nw["net_worth"]),
        "liquid_cash": float(nw["liquid_cash"]),
        "savings": float(nw["savings"]),
        "cc_debt": float(nw["cc_debt"]),
        "spending_by_category": spending,
        "account_balances": account_balances,
    }


@router.post("/financial/generate")
def financial_generate(
    req: ReportRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Build and return a Financial Report PDF."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_financial_pdf(db, p_start, p_end, label)

    filename = f"FinForge_Financial_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/financial/email")
def financial_email(
    req: ReportRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """Generate and email the Financial Report."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_financial_pdf(db, p_start, p_end, label)

    filename = f"FinForge_Financial_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    _email_pdf(
        buf,
        filename=filename,
        subject=f"FinForge Financial Report - {label}",
        body_text=f"Attached is your FinForge Financial Report for {label}.",
    )
    return {"status": "sent", "to": _TO_ADDR, "filename": filename}


def _build_financial_pdf(
    db: Session,
    p_start: date,
    p_end: date,
    label: str,
) -> io.BytesIO:
    """Assemble the full Financial Report PDF."""
    bal_pairs = _get_latest_balances(db, p_end)
    nw = _compute_net_worth(bal_pairs)
    spending = _spending_by_category(db, p_start, p_end)
    income_txns = _income_transactions(db, p_start, p_end)
    total_income = sum(abs(t.amount) for t in income_txns)
    total_spending = sum(Decimal(str(s["amount"])) for s in spending)

    pdf = FinForgePDFBuilder("Financial Report", subtitle=label)

    # ── Summary ──
    pdf.add_heading("Summary")
    pdf.add_summary_table([
        ("Net Worth", _currency(nw["net_worth"])),
        ("Liquid Cash", _currency(nw["liquid_cash"])),
        ("Savings & Investments", _currency(nw["savings"])),
        ("Credit Card Debt", _currency(nw["cc_debt"])),
        ("Total Income", _currency(total_income)),
        ("Total Spending", _currency(total_spending)),
    ])

    # ── Account Balances ──
    pdf.add_heading("Account Balances")
    pdf.add_data_table(
        headers=["Account", "Type", "Balance"],
        rows=[
            [acct.alias, acct.account_type.replace("_", " ").title(), _currency(bal.balance_amount)]
            for acct, bal in sorted(bal_pairs, key=lambda p: p[0].alias)
        ],
    )

    # ── Spending by Category ──
    if spending:
        pdf.add_heading("Spending by Category")
        pdf.add_data_table(
            headers=["Category", "Amount", "% of Total"],
            rows=[
                [
                    s["category"],
                    _currency(s["amount"]),
                    f"{s['amount'] / float(total_spending) * 100:.1f}%" if total_spending else "0%",
                ]
                for s in spending
            ],
        )
        cat_dict = {s["category"]: s["amount"] for s in spending}
        pie_fig = chart_builder.spending_pie_chart(cat_dict, title=f"Spending - {label}")
        pdf.add_chart(pie_fig)

    # ── Multi-month trends ──
    if _is_multi_month(p_start, p_end):
        months = _months_in_range(p_start, p_end)

        # Monthly spending trend
        month_labels: list[str] = []
        category_monthly: dict[str, list[float]] = defaultdict(list)
        all_cats: set[str] = set()

        for m_start, m_end in months:
            month_labels.append(m_start.strftime("%b %Y"))
            m_spending = _spending_by_category(db, m_start, m_end)
            m_map = {s["category"]: s["amount"] for s in m_spending}
            all_cats.update(m_map.keys())

        # Second pass to fill in zeros
        for m_start, m_end in months:
            m_spending = _spending_by_category(db, m_start, m_end)
            m_map = {s["category"]: s["amount"] for s in m_spending}
            for cat in sorted(all_cats):
                category_monthly[cat].append(m_map.get(cat, 0.0))

        if category_monthly:
            pdf.add_heading("Spending Trend")
            trend_fig = chart_builder.spending_trend_bar(
                month_labels, dict(category_monthly), title=f"Spending Trend - {label}"
            )
            pdf.add_chart(trend_fig)

        # Monthly income vs expenses
        income_monthly: list[float] = []
        expense_monthly: list[float] = []
        for m_start, m_end in months:
            m_inc = _income_transactions(db, m_start, m_end)
            income_monthly.append(float(sum(abs(t.amount) for t in m_inc)))
            m_exp = _spending_by_category(db, m_start, m_end)
            expense_monthly.append(sum(s["amount"] for s in m_exp))

        ie_fig = chart_builder.income_vs_expenses_bar(
            month_labels, income_monthly, expense_monthly,
            title=f"Income vs Expenses - {label}",
        )
        pdf.add_chart(ie_fig)

        # Net worth trend
        nw_dates: list[date] = []
        nw_values: list[float] = []
        for m_start, m_end in months:
            m_pairs = _get_latest_balances(db, m_end)
            m_nw = _compute_net_worth(m_pairs)
            nw_dates.append(m_end)
            nw_values.append(float(m_nw["net_worth"]))

        if nw_values:
            pdf.add_heading("Net Worth Trend")
            nw_fig = chart_builder.net_worth_line(nw_dates, nw_values, title=f"Net Worth - {label}")
            pdf.add_chart(nw_fig)

    return pdf.build()


# ═══════════════════════════════════════════════════════════════════════════
# TITHING REPORTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/tithing/income")
def tithing_income_preview(
    period: str = Query(default="monthly"),
    month: str = Query(default=""),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Preview income transactions for tithing computation.

    Each transaction is annotated with:
    - auto_checked: True if merchant contains 'Brigham Young' (employer income).
    - auto_excluded: True if merchant contains 'ERIC L BLATTER' (family transfer).
    """
    if not month and period != "custom":
        month = date.today().strftime("%Y-%m")

    p_start, p_end = _resolve_period(period, month, start_date, end_date)
    income_txns = _income_transactions(db, p_start, p_end)

    items = []
    for t in income_txns:
        merchant = (t.merchant_name or "").strip()
        merchant_lower = merchant.lower()
        items.append({
            "id": str(t.id),
            "date": t.date.isoformat(),
            "amount": float(abs(t.amount)),
            "merchant_name": merchant,
            "category": t.category,
            "auto_checked": "brigham young" in merchant_lower,
            "auto_excluded": "eric l blatter" in merchant_lower,
        })

    # Schwab holdings as in-kind donation suggestions
    schwab_accounts = (
        db.query(Account)
        .filter(Account.alias.in_(list(_SCHWAB_ALIASES)))
        .all()
    )
    schwab_ids = [a.id for a in schwab_accounts]

    holdings = []
    if schwab_ids:
        for acct_id in schwab_ids:
            latest_holding_date = (
                db.query(sqla_func.max(Holding.snapshot_date))
                .filter(Holding.account_id == acct_id)
                .scalar()
            )
            if latest_holding_date:
                acct_holdings = (
                    db.query(Holding)
                    .filter(
                        Holding.account_id == acct_id,
                        Holding.snapshot_date == latest_holding_date,
                    )
                    .all()
                )
                for h in acct_holdings:
                    holdings.append({
                        "symbol": h.symbol,
                        "quantity": float(h.quantity),
                        "market_value": float(h.market_value),
                        "cost_basis": float(h.cost_basis) if h.cost_basis else None,
                    })

    return {
        "period": period,
        "start_date": p_start.isoformat(),
        "end_date": p_end.isoformat(),
        "income_transactions": items,
        "donation_suggestions": holdings,
    }


@router.post("/tithing/generate")
def tithing_generate(
    req: TithingRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Build and return a Tithing Report PDF."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_tithing_pdf(db, p_start, p_end, label, req)

    filename = f"FinForge_Tithing_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tithing/email")
def tithing_email(
    req: TithingRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """Generate and email the Tithing Report."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_tithing_pdf(db, p_start, p_end, label, req)

    filename = f"FinForge_Tithing_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    _email_pdf(
        buf,
        filename=filename,
        subject=f"FinForge Tithing Report - {label}",
        body_text=f"Attached is your FinForge Tithing Report for {label}.",
    )
    return {"status": "sent", "to": _TO_ADDR, "filename": filename}


def _build_tithing_pdf(
    db: Session,
    p_start: date,
    p_end: date,
    label: str,
    req: TithingRequest,
) -> io.BytesIO:
    """Assemble the Tithing Report PDF."""
    # ── Selected income ──
    selected_ids = set(req.included_transaction_ids)
    income_txns = _income_transactions(db, p_start, p_end)

    if selected_ids:
        included = [t for t in income_txns if str(t.id) in selected_ids]
    else:
        # Default: auto-check BYU, exclude family transfers
        included = [
            t for t in income_txns
            if "brigham young" in (t.merchant_name or "").lower()
            and "eric l blatter" not in (t.merchant_name or "").lower()
        ]

    income_total = sum(abs(t.amount) for t in included)

    # ── In-kind donations ──
    in_kind_total = Decimal("0")
    for d in req.in_kind_donations:
        fmv = Decimal(str(d.get("fair_market_value", 0)))
        in_kind_total += fmv

    # ── Tithing target ──
    total_tithable = income_total + in_kind_total
    tithing_target = (total_tithable * Decimal("0.10")).quantize(Decimal("0.01"))

    # ── Tithing payments already made ──
    tithing_payments = (
        db.query(Transaction)
        .filter(
            Transaction.amount > 0,
            Transaction.is_pending == False,
            Transaction.date >= p_start,
            Transaction.date <= p_end,
        )
        .all()
    )
    tithing_paid = Decimal("0")
    tithing_payment_rows: list[Transaction] = []
    for t in tithing_payments:
        merchant_lower = (t.merchant_name or "").lower()
        if "church of jesus christ" in merchant_lower or "lds" in merchant_lower:
            tithing_paid += t.amount
            tithing_payment_rows.append(t)

    remaining = tithing_target - tithing_paid

    # ── Build PDF ──
    pdf = FinForgePDFBuilder("Tithing Report", subtitle=label)

    pdf.add_heading("Summary")
    pdf.add_summary_table([
        ("Tithable Income", _currency(income_total)),
        ("In-Kind Donations (FMV)", _currency(in_kind_total)),
        ("Total Tithable", _currency(total_tithable)),
        ("10% Tithing Target", _currency(tithing_target)),
        ("Tithing Paid", _currency(tithing_paid)),
        ("Remaining", _currency(remaining)),
    ])

    # ── Income table ──
    pdf.add_heading("Included Income")
    if included:
        pdf.add_data_table(
            headers=["Date", "Merchant", "Category", "Amount"],
            rows=[
                [
                    t.date.isoformat(),
                    t.merchant_name or "Unknown",
                    t.category or "",
                    _currency(abs(t.amount)),
                ]
                for t in included
            ],
        )
    else:
        pdf.add_text("No income transactions selected.")

    # ── In-kind donations table ──
    if req.in_kind_donations:
        pdf.add_heading("In-Kind Donations")
        pdf.add_data_table(
            headers=["Symbol", "Shares", "Fair Market Value"],
            rows=[
                [
                    str(d.get("symbol", "")),
                    str(d.get("shares", "")),
                    _currency(Decimal(str(d.get("fair_market_value", 0)))),
                ]
                for d in req.in_kind_donations
            ],
        )

    # ── Tithing payments ──
    pdf.add_heading("Tithing Payments")
    if tithing_payment_rows:
        pdf.add_data_table(
            headers=["Date", "Merchant", "Amount"],
            rows=[
                [
                    t.date.isoformat(),
                    t.merchant_name or "Unknown",
                    _currency(t.amount),
                ]
                for t in tithing_payment_rows
            ],
        )
    else:
        pdf.add_text("No tithing payments found in this period.")

    return pdf.build()


# ═══════════════════════════════════════════════════════════════════════════
# CONTRIBUTION REPORTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/contributions/preview")
def contributions_preview(
    period: str = Query(default="monthly"),
    month: str = Query(default=""),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """
    Preview Schwab contribution data.

    Transfers into Schwab accounts show as income (amount < 0) on those accounts.
    Classified as 'Dad' if merchant contains 'ERIC L BLATTER', else 'Nathan'.
    Also reports Roth IRA annual headroom vs the $7,000 limit.
    """
    if not month and period != "custom":
        month = date.today().strftime("%Y-%m")

    p_start, p_end = _resolve_period(period, month, start_date, end_date)

    schwab_accounts = (
        db.query(Account)
        .filter(Account.alias.in_(list(_SCHWAB_ALIASES)))
        .all()
    )
    schwab_map = {a.id: a for a in schwab_accounts}
    schwab_ids = list(schwab_map.keys())

    # Transfers into Schwab = amount < 0 (credit)
    transfers = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(schwab_ids),
            Transaction.amount < 0,
            Transaction.is_pending == False,
            Transaction.date >= p_start,
            Transaction.date <= p_end,
        )
        .order_by(Transaction.date)
        .all()
    )

    items = []
    for t in transfers:
        acct = schwab_map[t.account_id]
        merchant_lower = (t.merchant_name or "").lower()
        source = "Dad" if "eric l blatter" in merchant_lower else "Nathan"
        items.append({
            "id": str(t.id),
            "date": t.date.isoformat(),
            "amount": float(abs(t.amount)),
            "merchant_name": t.merchant_name,
            "account": acct.alias,
            "source": source,
        })

    # Roth IRA annual total
    roth_acct = db.query(Account).filter(Account.alias == _ROTH_IRA_ALIAS).first()
    roth_annual_total = Decimal("0")
    if roth_acct:
        year_start = date(p_end.year, 1, 1)
        year_end = date(p_end.year, 12, 31)
        roth_contributions = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == roth_acct.id,
                Transaction.amount < 0,
                Transaction.is_pending == False,
                Transaction.date >= year_start,
                Transaction.date <= year_end,
            )
            .all()
        )
        roth_annual_total = sum(abs(t.amount) for t in roth_contributions)

    roth_headroom = max(Decimal("0"), _ROTH_ANNUAL_LIMIT - roth_annual_total)

    return {
        "period": period,
        "start_date": p_start.isoformat(),
        "end_date": p_end.isoformat(),
        "contributions": items,
        "roth_ira_annual_total": float(roth_annual_total),
        "roth_ira_limit": float(_ROTH_ANNUAL_LIMIT),
        "roth_ira_headroom": float(roth_headroom),
    }


@router.post("/contributions/generate")
def contributions_generate(
    req: ContributionRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Build and return a Schwab Contributions Report PDF."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_contributions_pdf(db, p_start, p_end, label)

    filename = f"FinForge_Contributions_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/contributions/email")
def contributions_email(
    req: ContributionRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict:
    """Generate and email the Schwab Contributions Report."""
    if not req.month and req.period != "custom":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month is required for non-custom periods.",
        )

    p_start, p_end = _resolve_period(req.period, req.month, req.start_date, req.end_date)
    label = _period_label(p_start, p_end)
    buf = _build_contributions_pdf(db, p_start, p_end, label)

    filename = f"FinForge_Contributions_{p_start.isoformat()}_{p_end.isoformat()}.pdf"
    _email_pdf(
        buf,
        filename=filename,
        subject=f"FinForge Contributions Report - {label}",
        body_text=f"Attached is your FinForge Contributions Report for {label}.",
    )
    return {"status": "sent", "to": _TO_ADDR, "filename": filename}


def _build_contributions_pdf(
    db: Session,
    p_start: date,
    p_end: date,
    label: str,
) -> io.BytesIO:
    """Assemble the Schwab Contributions Report PDF."""
    schwab_accounts = (
        db.query(Account)
        .filter(Account.alias.in_(list(_SCHWAB_ALIASES)))
        .all()
    )
    schwab_map = {a.id: a for a in schwab_accounts}
    schwab_ids = list(schwab_map.keys())

    transfers = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(schwab_ids),
            Transaction.amount < 0,
            Transaction.is_pending == False,
            Transaction.date >= p_start,
            Transaction.date <= p_end,
        )
        .order_by(Transaction.date)
        .all()
    )

    # Classify
    rows_data: list[dict] = []
    nathan_total = Decimal("0")
    dad_total = Decimal("0")

    for t in transfers:
        acct = schwab_map[t.account_id]
        amt = abs(t.amount)
        merchant_lower = (t.merchant_name or "").lower()
        source = "Dad" if "eric l blatter" in merchant_lower else "Nathan"
        if source == "Dad":
            dad_total += amt
        else:
            nathan_total += amt
        rows_data.append({
            "date": t.date,
            "merchant": t.merchant_name or "Transfer",
            "account": acct.alias,
            "amount": amt,
            "source": source,
        })

    period_total = nathan_total + dad_total

    # Roth IRA annual
    roth_acct = db.query(Account).filter(Account.alias == _ROTH_IRA_ALIAS).first()
    roth_annual_total = Decimal("0")
    roth_transfers_for_chart: list[Transaction] = []

    if roth_acct:
        year_start = date(p_end.year, 1, 1)
        year_end = date(p_end.year, 12, 31)
        roth_txns = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == roth_acct.id,
                Transaction.amount < 0,
                Transaction.is_pending == False,
                Transaction.date >= year_start,
                Transaction.date <= year_end,
            )
            .order_by(Transaction.date)
            .all()
        )
        roth_annual_total = sum(abs(t.amount) for t in roth_txns)
        roth_transfers_for_chart = roth_txns

    roth_headroom = max(Decimal("0"), _ROTH_ANNUAL_LIMIT - roth_annual_total)

    # ── Build PDF ──
    pdf = FinForgePDFBuilder("Contributions Report", subtitle=label)

    pdf.add_heading("Summary")
    pdf.add_summary_table([
        ("Total Contributions (Period)", _currency(period_total)),
        ("Nathan's Contributions", _currency(nathan_total)),
        ("Dad's Contributions", _currency(dad_total)),
        (f"Roth IRA ({p_end.year} YTD)", _currency(roth_annual_total)),
        ("Roth IRA Annual Limit", _currency(_ROTH_ANNUAL_LIMIT)),
        ("Roth IRA Headroom", _currency(roth_headroom)),
    ])

    # ── Contribution table ──
    pdf.add_heading("Contribution Details")
    if rows_data:
        pdf.add_data_table(
            headers=["Date", "Source", "Account", "Merchant", "Amount"],
            rows=[
                [
                    r["date"].isoformat(),
                    r["source"],
                    r["account"],
                    r["merchant"],
                    _currency(r["amount"]),
                ]
                for r in rows_data
            ],
        )
    else:
        pdf.add_text("No Schwab contributions found in this period.")

    # ── Timeline chart ──
    if roth_transfers_for_chart:
        chart_dates = [t.date for t in roth_transfers_for_chart]
        chart_amounts = [float(abs(t.amount)) for t in roth_transfers_for_chart]
        cumulative: list[float] = []
        running = 0.0
        for a in chart_amounts:
            running += a
            cumulative.append(running)

        pdf.add_heading(f"Roth IRA Contributions - {p_end.year}")
        timeline_fig = chart_builder.contribution_timeline(
            chart_dates,
            chart_amounts,
            cumulative,
            limit=float(_ROTH_ANNUAL_LIMIT),
            title=f"Roth IRA Contributions - {p_end.year}",
        )
        pdf.add_chart(timeline_fig)

    return pdf.build()
