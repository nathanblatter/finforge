"""
GET /api/v1/spending/monthly  — discretionary CC spend breakdown for a month
GET /api/v1/spending/transactions — filterable transaction feed
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from collections import defaultdict
from statistics import median

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, CategoryRule, SpendingAnomaly, Transaction
from schemas.schemas import (
    CardSpend,
    CategoryRuleCreate,
    CategoryRuleItem,
    CategoryRulesResponse,
    CategorySpend,
    FixedExpenses,
    MonthlySpendingResponse,
    SubscriptionItem,
    SubscriptionsResponse,
    TransactionCategoryUpdate,
    TransactionResponse,
)

router = APIRouter(tags=["spending"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_bounds(month_str: str) -> tuple[date, date]:
    """Parse YYYY-MM → (first_day, last_day)."""
    try:
        year, mon = int(month_str[:4]), int(month_str[5:7])
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid month format '{month_str}'. Expected YYYY-MM.",
        )
    first_day = date(year, mon, 1)
    if mon == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, mon + 1, 1) - timedelta(days=1)
    return first_day, last_day


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Monthly spending
# ---------------------------------------------------------------------------

@router.get("/spending/monthly", response_model=MonthlySpendingResponse)
def get_monthly_spending(
    month: str = Query(default=None, description="YYYY-MM — defaults to current month"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> MonthlySpendingResponse:
    """
    Discretionary CC spend for the month, broken down by category and card.
    Fixed expenses (rent, tuition) shown separately and excluded from discretionary total.
    Per PRD: CC spend pool = WF Credit Card + Amex Credit Card combined.
    """
    if month is None:
        month = _current_month()
    first_day, last_day = _month_bounds(month)

    cc_accounts = (
        db.query(Account)
        .filter(Account.account_type == "credit_card")
        .all()
    )
    cc_ids = [a.id for a in cc_accounts]
    alias_map: dict[uuid.UUID, str] = {a.id: a.alias for a in cc_accounts}

    # Discretionary = CC transactions, not fixed, not pending, within month
    discretionary = (
        db.query(Transaction)
        .filter(
            Transaction.account_id.in_(cc_ids),
            Transaction.is_fixed_expense == False,
            Transaction.is_pending == False,
            Transaction.date >= first_day,
            Transaction.date <= last_day,
        )
        .all()
    )

    total = sum(Decimal(str(t.amount)) for t in discretionary)

    # By category
    cat_totals: dict[str, Decimal] = {}
    for t in discretionary:
        cat = t.category or "Other"
        cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + Decimal(str(t.amount))

    by_category = [
        CategorySpend(
            category=cat,
            amount=amt,
            pct_of_total=(amt / total * 100).quantize(Decimal("0.01")) if total else Decimal("0"),
        )
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # By card (WF Credit Card and Amex separately per PRD)
    card_totals: dict[str, Decimal] = {}
    for t in discretionary:
        alias = alias_map.get(t.account_id, "Unknown")
        card_totals[alias] = card_totals.get(alias, Decimal("0")) + Decimal(str(t.amount))

    by_card = [CardSpend(alias=a, amount=v) for a, v in sorted(card_totals.items())]

    # Fixed expenses (from ALL accounts, not just CC)
    fixed_txns = (
        db.query(Transaction)
        .filter(
            Transaction.is_fixed_expense == True,
            Transaction.date >= first_day,
            Transaction.date <= last_day,
        )
        .all()
    )
    rent = Decimal("0")
    tuition = Decimal("0")
    for t in fixed_txns:
        cat = (t.category or "").strip().lower()
        amt = Decimal(str(t.amount))
        if cat == "housing":
            rent += amt
        elif cat == "education":
            tuition += amt

    return MonthlySpendingResponse(
        month=month,
        total_discretionary=total,
        by_category=by_category,
        by_card=by_card,
        fixed_expenses=FixedExpenses(rent=rent, tuition=tuition, total=rent + tuition),
        transaction_count=len(discretionary),
    )


# ---------------------------------------------------------------------------
# Transaction feed
# ---------------------------------------------------------------------------

@router.get("/spending/transactions", response_model=list[TransactionResponse])
def get_transactions(
    days: int = Query(default=30, ge=1, description="Last N days"),
    category: str | None = Query(default=None, description="Filter by FinForge category"),
    account_alias: str | None = Query(default=None, description="Filter by account alias"),
    include_pending: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> list[TransactionResponse]:
    """
    Filterable transaction feed across all accounts.
    account_alias returned in response — account_id and plaid_transaction_id never exposed.
    """
    since = date.today() - timedelta(days=days)

    q = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Transaction.date >= since)
    )
    if not include_pending:
        q = q.filter(Transaction.is_pending == False)
    if category:
        q = q.filter(Transaction.category == category)
    if account_alias:
        q = q.filter(Account.alias == account_alias)

    rows = q.order_by(Transaction.date.desc()).limit(limit).all()

    return [
        TransactionResponse(
            id=t.id,
            date=t.date,
            amount=Decimal(str(t.amount)),
            merchant_name=t.merchant_name,
            category=t.category,
            subcategory=t.subcategory,
            is_pending=t.is_pending,
            is_fixed_expense=t.is_fixed_expense,
            category_overridden=t.category_overridden,
            account_alias=a.alias,
            notes=t.notes,
        )
        for t, a in rows
    ]


# ---------------------------------------------------------------------------
# Recategorization + rules
# ---------------------------------------------------------------------------

@router.patch("/spending/transactions/{txn_id}", response_model=TransactionResponse)
def update_transaction_category(
    txn_id: uuid.UUID,
    body: TransactionCategoryUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> TransactionResponse:
    """Manually set a transaction's category. Marks it as overridden so the
    Plaid sync won't clobber it."""
    category = body.category.strip()
    if not category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is required")

    row = db.query(Transaction, Account).join(Account, Transaction.account_id == Account.id).filter(Transaction.id == txn_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    t, a = row
    t.category = category
    t.category_overridden = True
    db.commit()
    db.refresh(t)
    return TransactionResponse(
        id=t.id, date=t.date, amount=Decimal(str(t.amount)), merchant_name=t.merchant_name,
        category=t.category, subcategory=t.subcategory, is_pending=t.is_pending,
        is_fixed_expense=t.is_fixed_expense, category_overridden=t.category_overridden,
        account_alias=a.alias, notes=t.notes,
    )


@router.get("/spending/rules", response_model=CategoryRulesResponse)
def list_rules(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> CategoryRulesResponse:
    rules = db.query(CategoryRule).order_by(CategoryRule.merchant).all()
    return CategoryRulesResponse(rules=[CategoryRuleItem.model_validate(r) for r in rules])


@router.post("/spending/rules", response_model=CategoryRuleItem, status_code=status.HTTP_201_CREATED)
def create_rule(
    body: CategoryRuleCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> CategoryRuleItem:
    """Create or update a merchant→category rule and apply it to all existing
    transactions from that merchant (case-insensitive)."""
    merchant = body.merchant.strip()
    category = body.category.strip()
    if not merchant or not category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Merchant and category are required")

    rule = db.query(CategoryRule).filter(func.lower(CategoryRule.merchant) == merchant.lower()).first()
    if rule is None:
        rule = CategoryRule(merchant=merchant, category=category)
        db.add(rule)
    else:
        rule.category = category

    # Apply to existing transactions from this merchant.
    db.query(Transaction).filter(func.lower(Transaction.merchant_name) == merchant.lower()).update(
        {Transaction.category: category, Transaction.category_overridden: True},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(rule)
    return CategoryRuleItem.model_validate(rule)


@router.delete("/spending/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> None:
    rule = db.query(CategoryRule).filter_by(id=rule_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()


# ---------------------------------------------------------------------------
# Subscriptions / recurring-charge detection
# ---------------------------------------------------------------------------

@router.get("/spending/subscriptions", response_model=SubscriptionsResponse)
def get_subscriptions(
    months: int = Query(default=6, ge=2, le=24, description="Lookback window in months"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> SubscriptionsResponse:
    """Heuristically detect recurring merchants: a charge that appears in at
    least 3 distinct months with reasonably consistent amounts."""
    since = date.today() - timedelta(days=months * 31)
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.date >= since,
            Transaction.is_pending.is_(False),
            Transaction.merchant_name.isnot(None),
            Transaction.amount > 0,  # debits only
        )
        .all()
    )

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for t in txns:
        groups[t.merchant_name.strip()].append(t)

    items: list[SubscriptionItem] = []
    for merchant, ts in groups.items():
        amounts = [float(t.amount) for t in ts]
        distinct_months = {(t.date.year, t.date.month) for t in ts}
        if len(distinct_months) < 3:
            continue
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        # Consistency check: ignore merchants with wildly varying charges.
        spread = (max(amounts) - min(amounts)) / avg
        if spread > 0.5:
            continue
        med = median(amounts)
        last = max(t.date for t in ts)
        # Most common category for the group
        cats = [t.category for t in ts if t.category]
        category = max(set(cats), key=cats.count) if cats else None
        items.append(SubscriptionItem(
            merchant=merchant,
            category=category,
            monthly_amount=Decimal(str(round(med, 2))),
            avg_amount=Decimal(str(round(avg, 2))),
            occurrences=len(ts),
            months_seen=len(distinct_months),
            last_date=last,
        ))

    items.sort(key=lambda s: s.monthly_amount, reverse=True)
    monthly_total = sum((s.monthly_amount for s in items), Decimal("0"))
    return SubscriptionsResponse(subscriptions=items, monthly_total=monthly_total)


# ---------------------------------------------------------------------------
# Category forecast — Holt's linear exponential smoothing per category
# ---------------------------------------------------------------------------

def _holt_forecast(series: list[float], alpha: float = 0.5, beta: float = 0.3) -> tuple[float, float]:
    """One-step-ahead Holt forecast. Returns (forecast, residual_std)."""
    level = series[0]
    trend = series[1] - series[0] if len(series) > 1 else 0.0
    residuals = []
    for y in series[1:]:
        pred = level + trend
        residuals.append(y - pred)
        new_level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    forecast = max(0.0, level + trend)
    if len(residuals) >= 2:
        mean_r = sum(residuals) / len(residuals)
        var = sum((r - mean_r) ** 2 for r in residuals) / (len(residuals) - 1)
        std = var ** 0.5
    else:
        std = 0.0
    return forecast, std


@router.get("/spending/forecast")
def get_spending_forecast(
    months: int = Query(default=12, ge=4, le=24, description="History window (complete months)"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Next-month spend forecast per category with an 80% confidence band,
    plus this month's run-rate projection. Excludes Investment Transfer."""
    today = date.today()
    first_of_current = today.replace(day=1)

    # Trailing N complete months
    start_year = first_of_current.year
    start_month = first_of_current.month - months
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    history_start = date(start_year, start_month, 1)

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.date >= history_start,
            Transaction.is_pending.is_(False),
            Transaction.amount > 0,
        )
        .all()
    )

    # Build per-category monthly totals over the complete-month window
    month_keys: list[str] = []
    y, m = history_start.year, history_start.month
    while (y, m) < (first_of_current.year, first_of_current.month):
        month_keys.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1

    by_cat_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    mtd: dict[str, float] = defaultdict(float)
    for t in txns:
        cat = t.category or "Other"
        if cat == "Investment Transfer":
            continue
        key = f"{t.date.year:04d}-{t.date.month:02d}"
        if t.date >= first_of_current:
            mtd[cat] += float(t.amount)
        elif key in month_keys:
            by_cat_month[cat][key] += float(t.amount)

    days_in_month = (date(today.year + (today.month == 12), (today.month % 12) + 1, 1) - first_of_current).days
    pace_factor = days_in_month / max(today.day, 1)

    categories = []
    for cat, month_map in sorted(by_cat_month.items()):
        series = [month_map.get(k, 0.0) for k in month_keys]
        # Skip categories with almost no history
        if sum(1 for v in series if v > 0) < 3:
            continue
        forecast, std = _holt_forecast(series)
        band = 1.28 * std  # ~80% interval
        spent = mtd.get(cat, 0.0)
        categories.append({
            "category": cat,
            "forecast": round(forecast, 2),
            "lo": round(max(0.0, forecast - band), 2),
            "hi": round(forecast + band, 2),
            "mtd_spent": round(spent, 2),
            "mtd_projected": round(spent * pace_factor, 2),
            "trailing_avg": round(sum(series) / len(series), 2),
            "history": [
                {"month": k, "amount": round(v, 2)}
                for k, v in zip(month_keys, series)
            ],
        })

    categories.sort(key=lambda c: c["forecast"], reverse=True)
    return {
        "forecast_month": (first_of_current.replace(day=28) + timedelta(days=4)).strftime("%Y-%m"),
        "current_month": first_of_current.strftime("%Y-%m"),
        "total_forecast": round(sum(c["forecast"] for c in categories), 2),
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# Spending anomalies
# ---------------------------------------------------------------------------

@router.get("/spending/anomalies")
def get_spending_anomalies(
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Recently flagged anomalous transactions (outliers and duplicates)."""
    q = (
        db.query(SpendingAnomaly, Transaction, Account)
        .join(Transaction, SpendingAnomaly.transaction_id == Transaction.id)
        .join(Account, Transaction.account_id == Account.id)
    )
    if not include_dismissed:
        q = q.filter(SpendingAnomaly.is_dismissed.is_(False))
    rows = q.order_by(SpendingAnomaly.created_at.desc()).limit(limit).all()

    return {
        "anomalies": [
            {
                "id": str(a.id),
                "transaction_id": str(t.id),
                "reason": a.reason,
                "z_score": float(a.z_score) if a.z_score is not None else None,
                "typical_amount": float(a.typical_amount) if a.typical_amount is not None else None,
                "detail": a.detail,
                "is_dismissed": a.is_dismissed,
                "created_at": a.created_at.isoformat(),
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "merchant_name": t.merchant_name,
                "category": t.category,
                "account_alias": acct.alias,
            }
            for a, t, acct in rows
        ]
    }


@router.post("/spending/anomalies/{anomaly_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_anomaly(
    anomaly_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> None:
    row = db.query(SpendingAnomaly).filter_by(id=anomaly_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")
    row.is_dismissed = True
    db.commit()
