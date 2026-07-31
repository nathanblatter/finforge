"""Shared recurring-transaction detection: bills (debits) and income/paychecks
(checking-account credits).

This is the single implementation of the "does this merchant look recurring,
and when will it fire next" heuristic. It originated in
``routers/spending.py``'s bills-forecast endpoint and is factored out here so
other features (e.g. the cash-flow runway forecast) can reuse the exact same
detection instead of re-deriving it.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Optional

from sqlalchemy.orm import Session

from models.db_models import Account, Transaction

# Checking debits in these categories are CC payments / transfers whose
# underlying charges are already projected individually — skip to avoid
# double counting.
BILL_EXCLUDED_CATEGORIES = {"credit card payment", "payment", "transfer", "investment transfer"}

# Bills must be ~monthly or sparser; income may be biweekly (paychecks).
BILL_MIN_GAP_DAYS = 20
INCOME_MIN_GAP_DAYS = 6

# How far back to look for recurrence patterns.
LOOKBACK_DAYS = 210


def predict_occurrences(
    txns: list[Transaction], today: date, horizon: date, min_gap: int
) -> Optional[tuple[float, list[date], int]]:
    """If a merchant's charges look recurring, return (median amount,
    predicted dates within [today, horizon], cadence days). None otherwise."""
    dates = sorted({t.date for t in txns})
    if len(dates) < 3:
        return None
    if len({(d.year, d.month) for d in dates}) < 3:
        return None
    amounts = [abs(float(t.amount)) for t in txns]
    med = median(amounts)
    if med <= 0:
        return None
    if (max(amounts) - min(amounts)) / med > 0.4:
        return None
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    gap = round(median(gaps))
    # Below min_gap is habitual spending (the same lunch order every week),
    # not a bill; >quarterly is too sparse to predict from a 7-month window.
    if gap < min_gap or gap > 95:
        return None
    nxt = dates[-1] + timedelta(days=gap)
    while nxt < today:
        nxt += timedelta(days=gap)
    occurrences = []
    while nxt <= horizon:
        occurrences.append(nxt)
        nxt += timedelta(days=gap)
    if not occurrences:
        return None
    return med, occurrences, gap


def load_recurring_groups(
    db: Session, today: date, horizon: date
) -> tuple[dict[str, list[Transaction]], dict[str, list[Transaction]]]:
    """Pull the last LOOKBACK_DAYS of non-pending transactions and bucket them
    into (bill_groups, income_groups) by merchant, ready for
    ``predict_occurrences``. Bills are checking/credit-card debits; income is
    checking-account credits."""
    since = today - timedelta(days=LOOKBACK_DAYS)

    rows = (
        db.query(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.date >= since,
            Transaction.is_pending.is_(False),
            Transaction.merchant_name.isnot(None),
        )
        .all()
    )

    bill_groups: dict[str, list[Transaction]] = defaultdict(list)
    income_groups: dict[str, list[Transaction]] = defaultdict(list)
    for t, a in rows:
        amt = float(t.amount)
        cat = (t.category or "").strip().lower()
        if cat in BILL_EXCLUDED_CATEGORIES:
            continue
        if amt > 0:
            bill_groups[t.merchant_name.strip()].append(t)
        elif amt < 0 and a.account_type == "checking":
            income_groups[t.merchant_name.strip()].append(t)

    return bill_groups, income_groups


def project_recurring_events(db: Session, today: date, horizon: date) -> list[dict]:
    """Detect recurring bills + income and project their occurrences into
    [today, horizon]. Returns a list of event dicts sorted chronologically
    (bills before income on the same day, so a running balance is
    conservative): {date, merchant, amount, kind, category, cadence_days}."""
    bill_groups, income_groups = load_recurring_groups(db, today, horizon)

    events: list[dict] = []
    for merchant, ts in bill_groups.items():
        pred = predict_occurrences(ts, today, horizon, min_gap=BILL_MIN_GAP_DAYS)
        if pred is None:
            continue
        amount, dates_due, gap = pred
        cats = [t.category for t in ts if t.category]
        category = max(set(cats), key=cats.count) if cats else None
        for d in dates_due:
            events.append({
                "date": d,
                "merchant": merchant,
                "amount": -round(amount, 2),
                "kind": "bill",
                "category": category,
                "cadence_days": gap,
            })
    for merchant, ts in income_groups.items():
        pred = predict_occurrences(ts, today, horizon, min_gap=INCOME_MIN_GAP_DAYS)
        if pred is None:
            continue
        amount, dates_due, gap = pred
        for d in dates_due:
            events.append({
                "date": d,
                "merchant": merchant,
                "amount": round(amount, 2),
                "kind": "income",
                "category": None,
                "cadence_days": gap,
            })

    events.sort(key=lambda e: (e["date"], e["amount"]))
    return events


def current_checking_balance(db: Session) -> Optional[float]:
    """Sum of the latest Balance row for each active checking account."""
    from models.db_models import Balance  # local import avoids a cycle at module import time

    checking = db.query(Account).filter(Account.account_type == "checking", Account.is_active.is_(True)).all()
    balances = []
    for acct in checking:
        latest = (
            db.query(Balance)
            .filter_by(account_id=acct.id)
            .order_by(Balance.balance_date.desc(), Balance.created_at.desc())
            .first()
        )
        if latest is not None:
            balances.append(float(latest.balance_amount))
    if not balances:
        return None
    return round(sum(balances), 2)
