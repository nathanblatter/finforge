"""
GET /api/v1/spending/monthly  — discretionary CC spend breakdown for a month
GET /api/v1/spending/transactions — filterable transaction feed
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from collections import defaultdict
from statistics import median

from database import get_db
from dependencies import verify_api_key
from models.db_models import Account, Balance, Budget, CategoryRule, SpendingAnomaly, Transaction
from services.recurring import current_checking_balance, project_recurring_events
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
    TransactionMetaUpdate,
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
    month: str | None = Query(default=None, description="YYYY-MM — overrides days"),
    category: str | None = Query(default=None, description="Filter by FinForge category"),
    account_alias: str | None = Query(default=None, description="Filter by account alias"),
    include_pending: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> list[TransactionResponse]:
    """
    Filterable transaction feed across all accounts.
    account_alias returned in response — account_id and plaid_transaction_id never exposed.
    """
    q = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
    )
    if month:
        first_day, last_day = _month_bounds(month)
        q = q.filter(Transaction.date >= first_day, Transaction.date <= last_day)
    else:
        q = q.filter(Transaction.date >= date.today() - timedelta(days=days))
    if not include_pending:
        q = q.filter(Transaction.is_pending == False)
    if category:
        q = q.filter(Transaction.category == category)
    if account_alias:
        q = q.filter(Account.alias == account_alias)

    rows = q.order_by(Transaction.date.desc()).limit(limit).all()

    return [_txn_response(t, a) for t, a in rows]


def _txn_response(t: Transaction, a: Account) -> TransactionResponse:
    return TransactionResponse(
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
        tags=list(t.tags or []),
    )


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
    return _txn_response(t, a)


@router.patch("/spending/transactions/{txn_id}/meta", response_model=TransactionResponse)
def update_transaction_meta(
    txn_id: uuid.UUID,
    body: TransactionMetaUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> TransactionResponse:
    """Set a transaction's note and/or tags. Omitted fields are left as-is;
    an empty string note or empty tags list clears the field."""
    row = db.query(Transaction, Account).join(Account, Transaction.account_id == Account.id).filter(Transaction.id == txn_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    t, a = row
    if body.notes is not None:
        t.notes = body.notes.strip() or None
    if body.tags is not None:
        cleaned = []
        for tag in body.tags:
            tag = tag.strip().lower().lstrip("#")[:50]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        if len(cleaned) > 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max 10 tags per transaction")
        t.tags = cleaned
    db.commit()
    db.refresh(t)
    return _txn_response(t, a)


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


# ---------------------------------------------------------------------------
# Daily spend heatmap
# ---------------------------------------------------------------------------

@router.get("/spending/daily")
def get_daily_spending(
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Daily discretionary spend totals for the heatmap calendar.
    Excludes fixed expenses and investment transfers so patterns show
    lifestyle spending, not rent day."""
    since = date.today() - timedelta(days=months * 31)
    rows = (
        db.query(Transaction.date, func.sum(Transaction.amount), func.count(Transaction.id))
        .filter(
            Transaction.date >= since,
            Transaction.is_pending.is_(False),
            Transaction.is_fixed_expense.is_(False),
            Transaction.amount > 0,
            (Transaction.category.is_(None)) | (Transaction.category != "Investment Transfer"),
        )
        .group_by(Transaction.date)
        .all()
    )
    return {
        "start": since.isoformat(),
        "days": [
            {"date": d.isoformat(), "total": round(float(total), 2), "count": int(n)}
            for d, total, n in sorted(rows)
        ],
    }


# ---------------------------------------------------------------------------
# Money flow (Sankey)
# ---------------------------------------------------------------------------

@router.get("/spending/flow")
def get_money_flow(
    month: str = Query(default=None, description="YYYY-MM — defaults to current month"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Income → fixed costs / spending categories / investing for one month,
    shaped as Sankey nodes and links."""
    if month is None:
        month = _current_month()
    first_day, last_day = _month_bounds(month)

    txns = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= first_day,
            Transaction.date <= last_day,
            Transaction.is_pending.is_(False),
        )
        .all()
    )

    income = 0.0
    fixed = 0.0
    investing = 0.0
    cat_totals: dict[str, float] = {}

    for t, a in txns:
        amt = float(t.amount)
        cat = t.category or "Other"
        if a.account_type == "checking" and amt < 0 and cat != "Investment Transfer":
            income += -amt  # deposits into checking
        elif amt > 0 and t.is_fixed_expense:
            fixed += amt
        elif amt > 0 and cat == "Investment Transfer" and a.account_type == "checking":
            investing += amt
        elif amt > 0 and a.account_type == "credit_card" and cat != "Investment Transfer":
            cat_totals[cat] = cat_totals.get(cat, 0.0) + amt

    # Top categories, rest folded into "Other"
    ranked = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    top_map: dict[str, float] = {}
    for k, v in ranked[:6]:
        top_map[k] = top_map.get(k, 0.0) + v
    leftover_cats = sum(v for _, v in ranked[6:])
    if leftover_cats > 0:
        top_map["Other"] = top_map.get("Other", 0.0) + leftover_cats

    outflows = fixed + investing + sum(top_map.values())

    nodes = [{"name": f"Income ({month})" if income > 0 else f"Spending ({month})"}]
    links = []

    def _add(name: str, value: float) -> None:
        if value <= 0:
            return
        nodes.append({"name": name})
        links.append({"source": 0, "target": len(nodes) - 1, "value": round(value, 2)})

    _add("Fixed Costs", fixed)
    _add("Investing", investing)
    for k, v in sorted(top_map.items(), key=lambda x: x[1], reverse=True):
        _add(k, v)
    if income > outflows:
        _add("Unallocated", income - outflows)

    return {
        "month": month,
        "income": round(income, 2),
        "outflows": round(outflows, 2),
        "nodes": nodes,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------

@router.get("/spending/streaks")
def get_spending_streaks(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Budget discipline streaks over the last 90 days.

    A day is "under budget" when its discretionary CC spend is at or below
    the prorated daily budget (sum of monthly budgets / days in that month).
    """
    import calendar as _cal

    today = date.today()
    since = today - timedelta(days=90)

    total_budget = float(
        db.query(func.coalesce(func.sum(Budget.monthly_limit), 0)).scalar() or 0
    )

    cc_ids = [a.id for a in db.query(Account).filter(Account.account_type == "credit_card").all()]
    rows = (
        db.query(Transaction.date, func.sum(Transaction.amount))
        .filter(
            Transaction.account_id.in_(cc_ids),
            Transaction.date >= since,
            Transaction.date <= today,
            Transaction.is_pending.is_(False),
            Transaction.is_fixed_expense.is_(False),
            Transaction.amount > 0,
            (Transaction.category.is_(None)) | (Transaction.category != "Investment Transfer"),
        )
        .group_by(Transaction.date)
        .all()
    )
    spend_by_day = {d: float(total) for d, total in rows}

    def _daily_budget(d: date) -> float:
        return total_budget / _cal.monthrange(d.year, d.month)[1] if total_budget > 0 else 0.0

    current_streak = 0
    longest_streak = 0
    run = 0
    no_spend_month = 0
    no_spend_90d = 0

    d = since
    while d <= today:
        spent = spend_by_day.get(d, 0.0)
        under = (spent <= _daily_budget(d)) if total_budget > 0 else (spent == 0.0)
        if under:
            run += 1
            longest_streak = max(longest_streak, run)
        else:
            run = 0
        if spent == 0.0:
            no_spend_90d += 1
            if d.year == today.year and d.month == today.month:
                no_spend_month += 1
        d += timedelta(days=1)
    current_streak = run

    return {
        "has_budgets": total_budget > 0,
        "daily_budget": round(_daily_budget(today), 2),
        "current_under_budget_streak": current_streak,
        "longest_streak_90d": longest_streak,
        "no_spend_days_this_month": no_spend_month,
        "no_spend_days_90d": no_spend_90d,
    }


# ---------------------------------------------------------------------------
# Global search (command palette)
# ---------------------------------------------------------------------------

@router.get("/spending/search")
def search_spending(
    q: str = Query(min_length=2, max_length=80),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Search merchants and transactions by name/category over the last year."""
    like = f"%{q.strip()}%"
    since = date.today() - timedelta(days=365)

    merchant_rows = (
        db.query(
            Transaction.merchant_name,
            func.count(Transaction.id),
            func.sum(Transaction.amount),
            func.max(Transaction.date),
        )
        .filter(
            Transaction.merchant_name.ilike(like),
            Transaction.date >= since,
            Transaction.is_pending.is_(False),
            Transaction.amount > 0,
        )
        .group_by(Transaction.merchant_name)
        .order_by(func.count(Transaction.id).desc())
        .limit(8)
        .all()
    )

    txn_rows = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= since,
            (Transaction.merchant_name.ilike(like)) | (Transaction.category.ilike(like)),
        )
        .order_by(Transaction.date.desc())
        .limit(15)
        .all()
    )

    return {
        "merchants": [
            {
                "merchant": m,
                "count": int(n),
                "total": round(float(total), 2),
                "last_date": last.isoformat(),
            }
            for m, n, total, last in merchant_rows
        ],
        "transactions": [
            {
                "id": str(t.id),
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "merchant_name": t.merchant_name,
                "category": t.category,
                "account_alias": a.alias,
                "is_pending": t.is_pending,
            }
            for t, a in txn_rows
        ],
    }


# ---------------------------------------------------------------------------
# Merchant drill-down
# ---------------------------------------------------------------------------

@router.get("/spending/merchant")
def get_merchant_detail(
    name: str = Query(min_length=1, max_length=255),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Full history for one merchant: totals, monthly trend, recurrence,
    recent transactions. Matched case-insensitively on the exact name."""
    rows = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            func.lower(Transaction.merchant_name) == name.strip().lower(),
            Transaction.is_pending.is_(False),
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")

    canonical = rows[0][0].merchant_name
    debits = [t for t, _ in rows if float(t.amount) > 0]
    amounts = [float(t.amount) for t in debits]
    total_spent = sum(amounts)
    visits = len(debits)

    cats = [t.category for t, _ in rows if t.category]
    category = max(set(cats), key=cats.count) if cats else None
    rule = db.query(CategoryRule).filter(func.lower(CategoryRule.merchant) == name.strip().lower()).first()
    if rule:
        category = rule.category

    # Recurrence: same heuristic as the subscriptions view
    distinct_months = {(t.date.year, t.date.month) for t in debits}
    monthly_median = None
    is_recurring = False
    if visits >= 3 and len(distinct_months) >= 3 and amounts:
        med = median(amounts)
        if med > 0 and (max(amounts) - min(amounts)) / med <= 0.5:
            is_recurring = True
            monthly_median = round(med, 2)

    # Monthly trend over the trailing 12 months (zero-filled)
    today = date.today()
    month_keys: list[str] = []
    y, m = today.year, today.month
    for _i in range(12):
        month_keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    month_keys.reverse()
    by_month: dict[str, dict[str, float]] = {k: {"total": 0.0, "count": 0} for k in month_keys}
    for t in debits:
        key = f"{t.date.year:04d}-{t.date.month:02d}"
        if key in by_month:
            by_month[key]["total"] += float(t.amount)
            by_month[key]["count"] += 1

    return {
        "merchant": canonical,
        "category": category,
        "has_rule": rule is not None,
        "total_spent": round(total_spent, 2),
        "visits": visits,
        "avg_amount": round(total_spent / visits, 2) if visits else 0.0,
        "first_seen": min(t.date for t, _ in rows).isoformat(),
        "last_seen": max(t.date for t, _ in rows).isoformat(),
        "is_recurring": is_recurring,
        "monthly_median": monthly_median,
        "accounts": sorted({a.alias for _, a in rows}),
        "trend": [
            {"month": k, "total": round(by_month[k]["total"], 2), "count": by_month[k]["count"]}
            for k in month_keys
        ],
        "recent": [
            {
                "id": str(t.id),
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "category": t.category,
                "account_alias": a.alias,
            }
            for t, a in rows[:20]
        ],
    }


# ---------------------------------------------------------------------------
# Bill calendar / low-balance forecast
# ---------------------------------------------------------------------------
#
# Recurring bill/income detection lives in services/recurring.py (shared with
# the cash-flow runway forecast in routers/cashflow.py) — see that module for
# the clustering heuristic itself.

@router.get("/spending/bills-forecast")
def get_bills_forecast(
    days: int = Query(default=30, ge=7, le=60),
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Project recurring bills and income over the next N days against the
    current checking balance. Card charges are projected on their charge date
    (not the statement payment date), so the balance path is approximate."""
    today = date.today()
    horizon = today + timedelta(days=days)

    events = project_recurring_events(db, today, horizon)
    checking_balance = current_checking_balance(db)

    projected_low = None
    end_balance = None
    if checking_balance is not None:
        running = checking_balance
        low, low_date = running, today
        for e in events:
            running += e["amount"]
            e["balance_after"] = round(running, 2)
            if running < low:
                low, low_date = running, e["date"]
        projected_low = {"date": low_date.isoformat(), "balance": round(low, 2)}
        end_balance = round(running, 2)
    else:
        for e in events:
            e["balance_after"] = None

    for e in events:
        e["date"] = e["date"].isoformat()

    return {
        "as_of": today.isoformat(),
        "days": days,
        "checking_balance": checking_balance,
        "events": events,
        "projected_low": projected_low,
        "projected_end_balance": end_balance,
    }
