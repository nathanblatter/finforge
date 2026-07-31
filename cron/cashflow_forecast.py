"""Cash-flow runway projection for the cron container.

The cron container doesn't import the `api` package (see db.py's module
docstring), so this mirrors the projection logic in
`api/services/recurring.py` + `api/routers/cashflow.py` using the cron-local
`db.py` Row classes. Keep the heuristics (recurring-charge clustering,
confidence-band sizing) identical to that module if either changes.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median, pstdev
from typing import Optional

from sqlalchemy.orm import Session

from db import AccountRow, BalanceRow, TransactionRow

BILL_EXCLUDED_CATEGORIES = {"credit card payment", "payment", "transfer", "investment transfer"}
BILL_MIN_GAP_DAYS = 20
INCOME_MIN_GAP_DAYS = 6
LOOKBACK_DAYS = 210
DISCRETIONARY_LOOKBACK_DAYS = 90
BAND_Z = 1.0


def _predict_occurrences(
    txns: list, today: date, horizon: date, min_gap: int
) -> Optional[tuple[float, list[date], int]]:
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


def _project_recurring_events(session: Session, today: date, horizon: date) -> list[dict]:
    since = today - timedelta(days=LOOKBACK_DAYS)
    rows = (
        session.query(TransactionRow, AccountRow)
        .join(AccountRow, TransactionRow.account_id == AccountRow.id)
        .filter(
            TransactionRow.date >= since,
            TransactionRow.is_pending.is_(False),
            TransactionRow.merchant_name.isnot(None),
        )
        .all()
    )

    bill_groups: dict[str, list] = defaultdict(list)
    income_groups: dict[str, list] = defaultdict(list)
    for t, a in rows:
        amt = float(t.amount)
        cat = (t.category or "").strip().lower()
        if cat in BILL_EXCLUDED_CATEGORIES:
            continue
        if amt > 0:
            bill_groups[t.merchant_name.strip()].append(t)
        elif amt < 0 and a.account_type == "checking":
            income_groups[t.merchant_name.strip()].append(t)

    events: list[dict] = []
    for merchant, ts in bill_groups.items():
        pred = _predict_occurrences(ts, today, horizon, min_gap=BILL_MIN_GAP_DAYS)
        if pred is None:
            continue
        amount, dates_due, gap = pred
        for d in dates_due:
            events.append({"date": d, "merchant": merchant, "amount": -round(amount, 2), "kind": "bill"})
    for merchant, ts in income_groups.items():
        pred = _predict_occurrences(ts, today, horizon, min_gap=INCOME_MIN_GAP_DAYS)
        if pred is None:
            continue
        amount, dates_due, gap = pred
        for d in dates_due:
            events.append({"date": d, "merchant": merchant, "amount": round(amount, 2), "kind": "income"})

    events.sort(key=lambda e: (e["date"], e["amount"]))
    return events


def _current_checking_balance(session: Session) -> Optional[float]:
    checking = session.query(AccountRow).filter(AccountRow.account_type == "checking", AccountRow.is_active.is_(True)).all()
    balances = []
    for acct in checking:
        latest = (
            session.query(BalanceRow)
            .filter_by(account_id=acct.id)
            .order_by(BalanceRow.balance_date.desc(), BalanceRow.created_at.desc())
            .first()
        )
        if latest is not None:
            balances.append(float(latest.balance_amount))
    if not balances:
        return None
    return round(sum(balances), 2)


def _discretionary_daily_series(session: Session, today: date, recurring_merchants: set) -> list[float]:
    since = today - timedelta(days=DISCRETIONARY_LOOKBACK_DAYS)
    rows = (
        session.query(TransactionRow, AccountRow)
        .join(AccountRow, TransactionRow.account_id == AccountRow.id)
        .filter(
            TransactionRow.date >= since,
            TransactionRow.date < today,
            TransactionRow.is_pending.is_(False),
            TransactionRow.amount > 0,
            AccountRow.account_type == "checking",
        )
        .all()
    )
    n_days = max((today - since).days, 1)
    by_day = {since + timedelta(days=d): 0.0 for d in range(n_days)}
    for t, a in rows:
        cat = (t.category or "").strip().lower()
        if cat in BILL_EXCLUDED_CATEGORIES:
            continue
        if t.merchant_name and t.merchant_name.strip() in recurring_merchants:
            continue
        by_day[t.date] = by_day.get(t.date, 0.0) + float(t.amount)
    return list(by_day.values())


def compute_runway(session: Session, days: int = 90) -> dict:
    """Same projection as GET /cashflow/runway, computed against the
    cron-local ORM. Returns checking_balance, floor-agnostic series, and the
    detected recurring events — floor comparison happens in the caller."""
    today = date.today()
    horizon = today + timedelta(days=days)

    events = _project_recurring_events(session, today, horizon)
    checking_balance = _current_checking_balance(session)

    recurring_merchants = {e["merchant"] for e in events}
    daily_discretionary = _discretionary_daily_series(session, today, recurring_merchants)
    daily_median = median(daily_discretionary) if daily_discretionary else 0.0
    daily_stdev = pstdev(daily_discretionary) if len(daily_discretionary) > 1 else 0.0

    events_by_date: dict[date, list[dict]] = defaultdict(list)
    for e in events:
        events_by_date[e["date"]].append(e)

    series = []
    if checking_balance is not None:
        running_central = checking_balance
        for i in range(1, days + 1):
            d = today + timedelta(days=i)
            for e in events_by_date.get(d, []):
                running_central += e["amount"]
            running_central -= daily_median
            uncertainty = BAND_Z * daily_stdev * (i ** 0.5)
            series.append({"date": d, "balance": running_central, "low": running_central - uncertainty})

    return {
        "as_of": today,
        "checking_balance": checking_balance,
        "series": series,  # [{date, balance, low}]
        "events": events,
    }
