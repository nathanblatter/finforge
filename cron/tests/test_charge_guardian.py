"""Unit tests for the Charge Guardian pure detector functions
(cron/charge_guardian.py). All tests run against synthetic transaction
fixtures — no database required."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from charge_guardian import (
    Txn,
    detect_duplicate_charges,
    detect_gray_charge_creep,
    detect_new_subscriptions,
    detect_trial_conversions,
    find_recurring_merchants,
    is_recurring_group,
    normalize_merchant,
)


def txn(merchant, amount, d, account_id=None):
    return Txn(
        id=uuid.uuid4(),
        date=d,
        amount=Decimal(str(amount)),
        merchant_name=merchant,
        account_id=account_id or uuid.uuid4(),
    )


def months_apart(start: date, n_months: int, day: int = 15) -> date:
    year = start.year + (start.month - 1 + n_months) // 12
    month = (start.month - 1 + n_months) % 12 + 1
    return date(year, month, day)


# ---------------------------------------------------------------------------
# normalize_merchant / recurrence heuristic
# ---------------------------------------------------------------------------

def test_normalize_merchant_strips_trailing_noise():
    assert normalize_merchant("NETFLIX.COM #4471") == normalize_merchant("netflix.com")
    assert normalize_merchant("  Spotify USA  ") == "spotify usa"


def test_is_recurring_group_requires_three_distinct_months_and_stable_amount():
    base = date(2026, 1, 15)
    stable = [txn("Netflix", "15.49", months_apart(base, i)) for i in range(4)]
    assert is_recurring_group(stable) is True

    two_months = [txn("Netflix", "15.49", months_apart(base, i)) for i in range(2)]
    assert is_recurring_group(two_months) is False

    volatile = [txn("Uber", amt, months_apart(base, i)) for i, amt in enumerate(["5", "45", "12", "60"])]
    assert is_recurring_group(volatile) is False


def test_find_recurring_merchants_groups_by_normalized_name():
    base = date(2026, 1, 15)
    txns = [txn("Netflix.com #123", "15.49", months_apart(base, i)) for i in range(3)]
    txns += [txn("Coffee Shop", "6.25", base)]
    recurring = find_recurring_merchants(txns)
    assert normalize_merchant("Netflix.com") in recurring
    assert normalize_merchant("Coffee Shop") not in recurring


# ---------------------------------------------------------------------------
# Detector 1: duplicate charges
# ---------------------------------------------------------------------------

def test_duplicate_charge_flagged_within_window():
    d1 = date(2026, 6, 1)
    a = txn("Amazon", "42.10", d1)
    b = txn("Amazon", "42.10", d1 + timedelta(days=2))
    findings = detect_duplicate_charges([a, b], recurring_merchants=set())
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "duplicate_charge"
    assert set(f.evidence_transaction_ids) == {a.id, b.id}


def test_duplicate_charge_allows_near_same_amount_within_tolerance():
    d1 = date(2026, 6, 1)
    a = txn("Amazon", "100.00", d1)
    b = txn("Amazon", "100.50", d1 + timedelta(days=1))  # within $1 / 2% tolerance
    findings = detect_duplicate_charges([a, b], recurring_merchants=set())
    assert len(findings) == 1


def test_duplicate_charge_not_flagged_outside_tolerance():
    d1 = date(2026, 6, 1)
    a = txn("Amazon", "100.00", d1)
    b = txn("Amazon", "110.00", d1 + timedelta(days=1))
    findings = detect_duplicate_charges([a, b], recurring_merchants=set())
    assert findings == []


def test_duplicate_charge_not_flagged_outside_window():
    d1 = date(2026, 6, 1)
    a = txn("Amazon", "42.10", d1)
    b = txn("Amazon", "42.10", d1 + timedelta(days=10))
    findings = detect_duplicate_charges([a, b], recurring_merchants=set())
    assert findings == []


def test_duplicate_charge_excludes_recurring_merchant():
    base = date(2026, 1, 15)
    recurring_txns = [txn("Netflix", "15.49", months_apart(base, i)) for i in range(3)]
    # A near-duplicate a couple days after the third recurring charge should
    # NOT be flagged as a duplicate — this merchant has an established cadence.
    dup = txn("Netflix", "15.49", recurring_txns[-1].date + timedelta(days=1))
    all_txns = recurring_txns + [dup]
    recurring_merchants = find_recurring_merchants(all_txns)
    findings = detect_duplicate_charges(all_txns, recurring_merchants=recurring_merchants)
    assert findings == []


def test_duplicate_charge_below_min_amount_ignored():
    d1 = date(2026, 6, 1)
    a = txn("Vending", "1.00", d1)
    b = txn("Vending", "1.00", d1 + timedelta(days=1))
    findings = detect_duplicate_charges([a, b], recurring_merchants=set(), min_amount=Decimal("2"))
    assert findings == []


def test_duplicate_charge_notes_cross_account():
    d1 = date(2026, 6, 1)
    acct1, acct2 = uuid.uuid4(), uuid.uuid4()
    a = txn("Amazon", "42.10", d1, account_id=acct1)
    b = txn("Amazon", "42.10", d1 + timedelta(days=1), account_id=acct2)
    findings = detect_duplicate_charges([a, b], recurring_merchants=set())
    assert "different accounts" in findings[0].detail


# ---------------------------------------------------------------------------
# Detector 2: new subscriptions
# ---------------------------------------------------------------------------

def test_new_subscription_flags_first_charge_of_recurring_merchant():
    base = date(2026, 1, 15)
    # Older unrelated history so the window demonstrably predates Hulu's
    # first charge (merchants whose first charge sits at the window edge are
    # skipped — their history may predate the data).
    history = [txn("Groceries", "80.00", date(2025, 9, 1))]
    txns = history + [txn("Hulu", "12.99", months_apart(base, i)) for i in range(3)]
    findings = detect_new_subscriptions(txns)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "new_subscription"
    first = min((t for t in txns if t.merchant_name == "Hulu"), key=lambda t: t.date)
    assert f.evidence_transaction_ids == [first.id]
    assert f.dedupe_key == f"new_subscription:{normalize_merchant('Hulu')}"


def test_new_subscription_ignores_non_recurring_merchant():
    txns = [txn("One-off Store", "50.00", date(2026, 1, 15))]
    assert detect_new_subscriptions(txns) == []


def test_new_subscription_dedupe_key_is_merchant_only():
    """dedupe_key has no date/period component so a later cron run (with the
    same merchant still recurring) produces the identical key — persistence
    layer relies on this to fire only once ever."""
    base = date(2026, 1, 15)
    history = [txn("Groceries", "80.00", date(2025, 9, 1))]
    txns = [txn("Hulu", "12.99", months_apart(base, i)) for i in range(4)]
    f1 = detect_new_subscriptions(history + txns[:3])[0]
    f2 = detect_new_subscriptions(history + txns)[0]
    assert f1.dedupe_key == f2.dedupe_key


# ---------------------------------------------------------------------------
# Detector 3: trial conversions
# ---------------------------------------------------------------------------

def test_trial_conversion_detected_within_window():
    auth = txn("Streamco", "0.00", date(2026, 1, 1))
    real = txn("Streamco", "9.99", date(2026, 1, 20))
    findings = detect_trial_conversions([auth, real])
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "trial_conversion"
    assert set(f.evidence_transaction_ids) == {auth.id, real.id}


def test_trial_conversion_matches_fuzzy_merchant_names():
    auth = txn("STREAMCO TRIAL", "1.00", date(2026, 1, 1))
    real = txn("Streamco", "9.99", date(2026, 1, 10))
    findings = detect_trial_conversions([auth, real])
    assert len(findings) == 1


def test_trial_conversion_ignored_outside_window():
    auth = txn("Streamco", "0.00", date(2026, 1, 1))
    real = txn("Streamco", "9.99", date(2026, 4, 1))  # >45 days later
    assert detect_trial_conversions([auth, real]) == []


def test_trial_conversion_ignored_when_not_first_real_charge():
    auth = txn("Streamco", "0.00", date(2026, 1, 1))
    earlier_real = txn("Streamco", "9.99", date(2025, 12, 1))
    later_real = txn("Streamco", "9.99", date(2026, 1, 20))
    findings = detect_trial_conversions([earlier_real, auth, later_real])
    assert findings == []


def test_trial_conversion_ignored_without_trial_auth():
    real = txn("Streamco", "9.99", date(2026, 1, 20))
    assert detect_trial_conversions([real]) == []


# ---------------------------------------------------------------------------
# Detector 4: gray-charge creep (digest)
# ---------------------------------------------------------------------------

def test_gray_charge_creep_flags_quiet_increase():
    base = date(2025, 2, 15)
    # Recurring merchant, price crept from $5.99 to $9.99 over 6 months —
    # still well under the $15 threshold so the price-hike detector's
    # consistency check (spread <= 20%) would reject it, but it's a real trend.
    amounts = ["5.99", "6.49", "6.99", "7.49", "7.99", "8.49", "8.99"]
    txns = [txn("Gray Co", amt, months_apart(base, i)) for i, amt in enumerate(amounts)]
    today = months_apart(base, len(amounts) - 1) + timedelta(days=5)
    findings = detect_gray_charge_creep(txns, today=today)
    assert len(findings) == 1
    assert findings[0].kind == "gray_charge_creep"
    assert "Gray Co" in findings[0].detail
    assert "creep" in findings[0].detail.lower() or "crept" in findings[0].detail.lower()


def test_gray_charge_creep_flags_newly_appeared_small_charge():
    today = date(2026, 6, 30)
    txns = [
        txn("New Small Sub", "4.99", today - timedelta(days=60)),
        txn("New Small Sub", "4.99", today - timedelta(days=30)),
        txn("New Small Sub", "4.99", today - timedelta(days=1)),
    ]
    findings = detect_gray_charge_creep(txns, today=today)
    assert len(findings) == 1
    assert "New Small Sub" in findings[0].detail
    assert "new" in findings[0].detail.lower()


def test_gray_charge_creep_ignores_charges_above_threshold():
    today = date(2026, 6, 30)
    txns = [txn("Big Sub", "40.00", today - timedelta(days=d)) for d in (60, 30, 1)]
    assert detect_gray_charge_creep(txns, today=today, threshold=Decimal("15")) == []


def test_gray_charge_creep_ignores_stable_established_charge():
    base = date(2025, 1, 15)
    txns = [txn("Stable Sub", "5.99", months_apart(base, i)) for i in range(8)]
    today = months_apart(base, 7) + timedelta(days=5)
    assert detect_gray_charge_creep(txns, today=today) == []


def test_gray_charge_creep_dedupe_key_buckets_by_month():
    today = date(2026, 6, 30)
    txns = [
        txn("New Small Sub", "4.99", today - timedelta(days=60)),
        txn("New Small Sub", "4.99", today - timedelta(days=30)),
        txn("New Small Sub", "4.99", today - timedelta(days=1)),
    ]
    f = detect_gray_charge_creep(txns, today=today)[0]
    assert f.dedupe_key == "gray_charge_creep:2026-06"


def test_gray_charge_creep_annualizes_cost():
    today = date(2026, 6, 30)
    txns = [
        txn("New Small Sub", "4.99", today - timedelta(days=60)),
        txn("New Small Sub", "4.99", today - timedelta(days=30)),
        txn("New Small Sub", "4.99", today - timedelta(days=1)),
    ]
    f = detect_gray_charge_creep(txns, today=today)[0]
    assert f.amount == Decimal("4.99") * 12


def test_new_subscription_skipped_when_first_charge_is_at_window_edge():
    """A merchant whose earliest charge sits within the history buffer of the
    oldest visible transaction may predate the data window — not "new"."""
    base = date(2026, 1, 15)
    txns = [txn("Netflix", "15.49", months_apart(base, i)) for i in range(4)]
    assert detect_new_subscriptions(txns) == []
