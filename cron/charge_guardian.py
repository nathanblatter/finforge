"""
Charge Guardian — fraud-style anomaly detection for FinForge cron.

Complements the price-hike detector (alerts_engine.run_check_subscription_hikes)
with detectors aimed at a different failure mode: not "my subscription got more
expensive" but "a charge shouldn't exist at all, or a subscription snuck in."

Four detectors, all pure functions over lists of transaction-like objects so
they can be unit tested against synthetic fixtures with no DB:

  1. detect_duplicate_charges   — same merchant, near-same amount, short window,
                                   excluding merchants with an established
                                   recurring cadence (those are handled by the
                                   price-hike detector instead).
  2. detect_new_subscriptions   — a merchant crosses the "recurring" bar for the
                                   first time; flag its first-ever charge as a
                                   new subscription. Cheap heuristic that also
                                   catches most trial conversions.
  3. detect_trial_conversions   — a merchant's first real charge follows a
                                   $0-$1 authorization from a similar merchant
                                   string within ~45 days (fires *before* three
                                   months of recurrence data exists, unlike #2).
  4. detect_gray_charge_creep   — small recurring charges (< threshold) that
                                   either newly appeared in the last 90 days or
                                   have quietly increased over 6 months.
                                   Reported as a single periodic digest finding.

Merchant grouping reuses the same normalization + recurrence heuristic as the
subscriptions view (api/routers/spending.py get_subscriptions) and the
price-hike detector (alerts_engine.run_check_subscription_hikes): >=3 distinct
calendar months, amount spread <=50% of the average.

Findings are persisted to charge_guardian_findings (one row per finding,
deduplicated by `dedupe_key` so a dismissed/marked-legit finding never
re-alerts) and surfaced through the same Notification + NateBot pipeline as
the other alert_engine/spending_anomalies detectors.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Iterable, Optional, Protocol

logger = logging.getLogger("finforge.cron.charge_guardian")


# ---------------------------------------------------------------------------
# Transaction protocol — detectors accept anything with these attributes
# (SQLAlchemy TransactionRow instances satisfy this by duck typing; tests use
# the plain Txn dataclass below).
# ---------------------------------------------------------------------------

class TxnLike(Protocol):
    id: uuid.UUID
    date: date
    amount: Decimal
    merchant_name: Optional[str]
    account_id: Optional[uuid.UUID]


@dataclass
class Txn:
    """Lightweight fixture transaction for tests and for constructing
    synthetic evidence; also satisfies TxnLike."""
    id: uuid.UUID
    date: date
    amount: Decimal
    merchant_name: Optional[str]
    account_id: Optional[uuid.UUID] = None


@dataclass
class Finding:
    kind: str
    merchant: str
    title: str
    detail: str
    evidence_transaction_ids: list[uuid.UUID]
    amount: Optional[Decimal]
    dedupe_key: str


# ---------------------------------------------------------------------------
# Merchant normalization + recurrence heuristic (shared across detectors,
# mirrors get_subscriptions() in api/routers/spending.py and
# run_check_subscription_hikes() in alerts_engine.py).
# ---------------------------------------------------------------------------

RECURRING_MIN_MONTHS = 3
RECURRING_SPREAD_MAX = 0.5  # (max-min)/avg must be <= this to call it "recurring"

_TRAILING_NOISE = re.compile(r"[\s#*0-9]+$")


def normalize_merchant(name: str) -> str:
    """Lowercase, strip, and drop trailing numeric/reference noise (e.g. Plaid
    appending a store number or auth code) so near-identical merchant strings
    group together."""
    n = name.strip().lower()
    n = _TRAILING_NOISE.sub("", n).strip()
    return n or name.strip().lower()


def _merchant_key(t: TxnLike) -> Optional[str]:
    if not t.merchant_name:
        return None
    return normalize_merchant(t.merchant_name)


def group_by_merchant(txns: Iterable[TxnLike]) -> dict[str, list[TxnLike]]:
    groups: dict[str, list[TxnLike]] = defaultdict(list)
    for t in txns:
        key = _merchant_key(t)
        if key is None:
            continue
        groups[key].append(t)
    return groups


def is_recurring_group(txns: list[TxnLike]) -> bool:
    """Same consistency check used by the subscriptions view: charges appear
    in >=3 distinct months with amounts that don't vary wildly."""
    amounts = [float(t.amount) for t in txns]
    distinct_months = {(t.date.year, t.date.month) for t in txns}
    if len(distinct_months) < RECURRING_MIN_MONTHS:
        return False
    avg = sum(amounts) / len(amounts)
    if avg <= 0:
        return False
    spread = (max(amounts) - min(amounts)) / avg
    return spread <= RECURRING_SPREAD_MAX


def find_recurring_merchants(txns: Iterable[TxnLike]) -> set[str]:
    """Normalized merchant keys that currently look recurring, over whatever
    window of transactions is passed in."""
    groups = group_by_merchant(txns)
    return {m for m, ts in groups.items() if is_recurring_group(ts)}


def _display_merchant(txns: list[TxnLike]) -> str:
    """Prefer the most recent raw merchant string for human-readable output."""
    return max(txns, key=lambda t: t.date).merchant_name.strip()


# ---------------------------------------------------------------------------
# Detector 1: duplicate charges
# ---------------------------------------------------------------------------

DUPLICATE_WINDOW_DAYS = 3
DUPLICATE_MIN_AMOUNT = Decimal("2")
DUPLICATE_AMOUNT_TOLERANCE_PCT = 0.02   # 2%
DUPLICATE_AMOUNT_TOLERANCE_ABS = Decimal("1.00")


def detect_duplicate_charges(
    txns: Iterable[TxnLike],
    recurring_merchants: Optional[set[str]] = None,
    window_days: int = DUPLICATE_WINDOW_DAYS,
    min_amount: Decimal = DUPLICATE_MIN_AMOUNT,
) -> list[Finding]:
    """Same merchant, same/near-same amount, within `window_days` days —
    excluding merchants with an established recurring cadence (those charges
    repeating monthly are supposed to happen; the price-hike detector already
    watches them for anomalies)."""
    all_txns = list(txns)
    if recurring_merchants is None:
        recurring_merchants = find_recurring_merchants(all_txns)

    groups = group_by_merchant(all_txns)
    findings: list[Finding] = []

    for merchant_key, ts in groups.items():
        if merchant_key in recurring_merchants:
            continue
        candidates = [t for t in ts if t.amount is not None and t.amount >= min_amount]
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda t: (t.date, str(t.id)))

        flagged_ids: set[uuid.UUID] = set()
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                a, b = candidates[i], candidates[j]
                if (b.date - a.date).days > window_days:
                    break  # sorted by date — nothing further in range
                if a.id in flagged_ids or b.id in flagged_ids:
                    continue
                tolerance = max(DUPLICATE_AMOUNT_TOLERANCE_ABS, a.amount * Decimal(str(DUPLICATE_AMOUNT_TOLERANCE_PCT)))
                if abs(a.amount - b.amount) > tolerance:
                    continue

                merchant_display = _display_merchant(ts)
                same_account = a.account_id == b.account_id
                pair_ids = sorted([a.id, b.id], key=str)
                detail = (
                    f"{merchant_display}: ${float(a.amount):,.2f} on {a.date} and "
                    f"${float(b.amount):,.2f} on {b.date}"
                    f"{' (same account)' if same_account else ' (different accounts)'} — "
                    f"{(b.date - a.date).days} day(s) apart."
                )
                findings.append(Finding(
                    kind="duplicate_charge",
                    merchant=merchant_display,
                    title=f"Possible duplicate charge: {merchant_display}",
                    detail=detail,
                    evidence_transaction_ids=pair_ids,
                    amount=max(a.amount, b.amount),
                    dedupe_key=f"duplicate_charge:{merchant_key}:{pair_ids[0]}:{pair_ids[1]}",
                ))
                flagged_ids.add(a.id)
                flagged_ids.add(b.id)

    return findings


# ---------------------------------------------------------------------------
# Detector 2: new subscriptions (also catches most trial conversions)
# ---------------------------------------------------------------------------

def detect_new_subscriptions(txns: Iterable[TxnLike]) -> list[Finding]:
    """Any merchant that currently qualifies as recurring — flag its
    first-ever charge as a new subscription. `dedupe_key` is merchant-only
    (no date/period component) so this fires exactly once per merchant, ever,
    regardless of how many times the cron job re-evaluates it."""
    groups = group_by_merchant(txns)
    findings: list[Finding] = []

    for merchant_key, ts in groups.items():
        if not is_recurring_group(ts):
            continue
        first = min(ts, key=lambda t: t.date)
        merchant_display = _display_merchant(ts)
        med = median(float(t.amount) for t in ts)
        detail = (
            f"{merchant_display} looks like a new recurring charge — first seen "
            f"{first.date}, now recurring at roughly ${med:,.2f}/mo."
        )
        findings.append(Finding(
            kind="new_subscription",
            merchant=merchant_display,
            title=f"New subscription started: {merchant_display}",
            detail=detail,
            evidence_transaction_ids=[first.id],
            amount=Decimal(str(round(med, 2))),
            dedupe_key=f"new_subscription:{merchant_key}",
        ))

    return findings


# ---------------------------------------------------------------------------
# Detector 3: trial-to-paid conversions
# ---------------------------------------------------------------------------

TRIAL_MAX_AMOUNT = Decimal("1.00")
TRIAL_WINDOW_DAYS = 45
TRIAL_FUZZY_MIN_LEN = 4


def _fuzzy_merchant_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) >= TRIAL_FUZZY_MIN_LEN and len(b) >= TRIAL_FUZZY_MIN_LEN:
        return a.startswith(b) or b.startswith(a)
    return False


def detect_trial_conversions(txns: Iterable[TxnLike]) -> list[Finding]:
    """A first-ever "real" charge (> TRIAL_MAX_AMOUNT) from a merchant whose
    name/pattern previously appeared at $0-$1 (a trial authorization) within
    TRIAL_WINDOW_DAYS days beforehand. Fires on the very first real charge,
    ahead of detect_new_subscriptions which needs ~3 months of history."""
    all_txns = sorted(txns, key=lambda t: t.date)
    trial_auths = [t for t in all_txns if t.merchant_name and Decimal("0") <= t.amount <= TRIAL_MAX_AMOUNT]
    real_charges = [t for t in all_txns if t.merchant_name and t.amount > TRIAL_MAX_AMOUNT]

    # First-ever real charge per normalized merchant key.
    first_real_by_merchant: dict[str, TxnLike] = {}
    for t in real_charges:
        key = normalize_merchant(t.merchant_name)
        if key not in first_real_by_merchant or t.date < first_real_by_merchant[key].date:
            first_real_by_merchant[key] = t

    findings: list[Finding] = []
    for merchant_key, real in first_real_by_merchant.items():
        # Any other real charge from this merchant before `real`? Then it's
        # not the first — skip (handled, if at all, by detect_new_subscriptions).
        earlier_real = any(
            normalize_merchant(t.merchant_name) == merchant_key and t.date < real.date
            for t in real_charges
        )
        if earlier_real:
            continue

        best_auth: Optional[TxnLike] = None
        for auth in trial_auths:
            if auth.id == real.id:
                continue
            days = (real.date - auth.date).days
            if not (0 <= days <= TRIAL_WINDOW_DAYS):
                continue
            if not _fuzzy_merchant_match(normalize_merchant(auth.merchant_name), merchant_key):
                continue
            if best_auth is None or auth.date > best_auth.date:
                best_auth = auth

        if best_auth is None:
            continue

        merchant_display = real.merchant_name.strip()
        detail = (
            f"{merchant_display}: a ${float(best_auth.amount):,.2f} authorization on "
            f"{best_auth.date} was followed {(real.date - best_auth.date).days} day(s) later by a "
            f"${float(real.amount):,.2f} charge on {real.date} — looks like a free trial converted to paid."
        )
        findings.append(Finding(
            kind="trial_conversion",
            merchant=merchant_display,
            title=f"Free trial converted to paid: {merchant_display}",
            detail=detail,
            evidence_transaction_ids=sorted([best_auth.id, real.id], key=str),
            amount=real.amount,
            dedupe_key=f"trial_conversion:{merchant_key}",
        ))

    return findings


# ---------------------------------------------------------------------------
# Detector 4: gray-charge creep (periodic digest)
# ---------------------------------------------------------------------------

GRAY_CHARGE_THRESHOLD = Decimal("15")
GRAY_CHARGE_NEW_WINDOW_DAYS = 90
GRAY_CHARGE_CREEP_MONTHS = 6
GRAY_CHARGE_CREEP_MIN_INCREASE_PCT = 0.10  # 10% since first charge in the window
GRAY_CHARGE_NEW_MIN_MONTHS = 2  # relaxed vs. RECURRING_MIN_MONTHS — 90-day window is short


@dataclass
class GrayChargeItem:
    merchant: str
    reason: str  # "new" | "creeping"
    current_amount: Decimal
    annualized: Decimal
    evidence_id: uuid.UUID
    detail: str


def _find_gray_charge_items(
    txns: list[TxnLike],
    today: date,
    threshold: Decimal,
) -> list[GrayChargeItem]:
    new_cutoff = today - timedelta(days=GRAY_CHARGE_NEW_WINDOW_DAYS)
    creep_cutoff = today - timedelta(days=30 * GRAY_CHARGE_CREEP_MONTHS)

    groups = group_by_merchant(txns)
    items: list[GrayChargeItem] = []

    for merchant_key, ts in groups.items():
        ts = sorted(ts, key=lambda t: t.date)
        latest = ts[-1]
        if latest.amount is None or latest.amount <= 0 or latest.amount >= threshold:
            continue
        merchant_display = _display_merchant(ts)

        first_seen = ts[0].date
        distinct_months = {(t.date.year, t.date.month) for t in ts}

        # (a) newly appeared: first charge within the last 90 days, with at
        # least a couple of occurrences so it's not just a one-off purchase.
        if first_seen >= new_cutoff and len(distinct_months) >= GRAY_CHARGE_NEW_MIN_MONTHS:
            annualized = latest.amount * 12
            items.append(GrayChargeItem(
                merchant=merchant_display,
                reason="new",
                current_amount=latest.amount,
                annualized=annualized,
                evidence_id=latest.id,
                detail=(
                    f"{merchant_display}: new small recurring charge, first seen {first_seen}, "
                    f"now ${float(latest.amount):,.2f}/mo (~${float(annualized):,.2f}/yr)."
                ),
            ))
            continue

        # (b) quietly increased over the creep window, still recurring overall.
        creep_window_txns = [t for t in ts if t.date >= creep_cutoff]
        if len(creep_window_txns) < 2 or not is_recurring_group(ts):
            continue
        earliest_in_window = creep_window_txns[0]
        if earliest_in_window.amount is None or earliest_in_window.amount <= 0:
            continue
        increase_pct = float((latest.amount - earliest_in_window.amount) / earliest_in_window.amount)
        if increase_pct < GRAY_CHARGE_CREEP_MIN_INCREASE_PCT:
            continue

        annualized = latest.amount * 12
        items.append(GrayChargeItem(
            merchant=merchant_display,
            reason="creeping",
            current_amount=latest.amount,
            annualized=annualized,
            evidence_id=latest.id,
            detail=(
                f"{merchant_display}: crept from ${float(earliest_in_window.amount):,.2f} "
                f"({earliest_in_window.date}) to ${float(latest.amount):,.2f} ({latest.date}), "
                f"+{increase_pct * 100:.0f}% over {GRAY_CHARGE_CREEP_MONTHS} months "
                f"(~${float(annualized):,.2f}/yr)."
            ),
        ))

    items.sort(key=lambda i: i.annualized, reverse=True)
    return items


def detect_gray_charge_creep(
    txns: Iterable[TxnLike],
    today: Optional[date] = None,
    threshold: Decimal = GRAY_CHARGE_THRESHOLD,
    period_key: Optional[str] = None,
) -> list[Finding]:
    """Small recurring charges under `threshold` that are new or have quietly
    increased. Returns a single digest Finding (or none) rather than one row
    per merchant — `period_key` (default: YYYY-MM of `today`) buckets the
    dedupe_key so the digest can re-fire next month even if this month's copy
    was dismissed, but won't duplicate within the same month."""
    today = today or date.today()
    items = _find_gray_charge_items(list(txns), today, threshold)
    if not items:
        return []

    period_key = period_key or today.strftime("%Y-%m")
    total_annualized = sum((i.annualized for i in items), Decimal("0"))
    lines = [i.detail for i in items[:15]]
    detail = (
        f"{len(items)} small recurring charge(s) under ${float(threshold):,.2f}/mo look worth a second look "
        f"(~${float(total_annualized):,.2f}/yr combined):\n" + "\n".join(f"- {line}" for line in lines)
    )
    finding = Finding(
        kind="gray_charge_creep",
        merchant="__digest__",
        title=f"Gray-charge digest: {len(items)} small charge(s) to review",
        detail=detail,
        evidence_transaction_ids=sorted({i.evidence_id for i in items}, key=str),
        amount=total_annualized,
        dedupe_key=f"gray_charge_creep:{period_key}",
    )
    return [finding]


# ---------------------------------------------------------------------------
# Orchestration — DB I/O + notification pipeline (not covered by unit tests;
# the detectors above are the testable surface).
# ---------------------------------------------------------------------------

DUPLICATE_LOOKBACK_DAYS = 120       # needs enough history to know what's "recurring"
SUBSCRIPTION_LOOKBACK_DAYS = 365    # matches ~12 months, enough for the 3-month bar
TRIAL_LOOKBACK_DAYS = 180
GRAY_CHARGE_LOOKBACK_DAYS = 30 * (GRAY_CHARGE_CREEP_MONTHS + 1)


def _persist_findings(session, findings: list[Finding]) -> list[Finding]:
    """Insert findings that aren't already known. Suppression rules:
      - a finding with the exact same dedupe_key already exists (open,
        dismissed, or legit) -> skip, it's already been surfaced once.
      - the merchant has a "legit" finding of the same kind -> skip, the
        user has permanently muted this merchant/kind combo.

    Returns the subset of `findings` that were newly inserted, so the caller
    can notify on exactly those.
    """
    from db import ChargeGuardianFindingRow

    if not findings:
        return []

    existing_keys = {
        r[0] for r in session.query(ChargeGuardianFindingRow.dedupe_key).all()
    }
    legit_merchant_kinds = {
        (r[0], r[1])
        for r in session.query(ChargeGuardianFindingRow.merchant, ChargeGuardianFindingRow.kind)
        .filter(ChargeGuardianFindingRow.status == "legit")
        .all()
    }

    now = datetime.now(timezone.utc)
    created: list[Finding] = []
    for f in findings:
        if f.dedupe_key in existing_keys:
            continue
        if (f.merchant, f.kind) in legit_merchant_kinds:
            continue
        session.add(ChargeGuardianFindingRow(
            id=uuid.uuid4(),
            kind=f.kind,
            merchant=f.merchant,
            dedupe_key=f.dedupe_key,
            title=f.title,
            detail=f.detail,
            evidence_transaction_ids=f.evidence_transaction_ids,
            amount=f.amount,
            status="open",
            created_at=now,
            updated_at=now,
        ))
        existing_keys.add(f.dedupe_key)  # in case detectors emit dup dedupe_keys in one run
        created.append(f)

    return created


NOTIFICATION_EMOJI = {
    "duplicate_charge": "🧾",
    "new_subscription": "🆕",
    "trial_conversion": "🎯",
    "gray_charge_creep": "🩶",
}


def run_charge_guardian() -> None:
    """Cron entrypoint: run all four detectors, persist new findings, and
    push notifications through the existing Notification + NateBot pipeline."""
    from db import NotificationRow, TransactionRow, get_session

    today = date.today()
    lookback_days = max(
        DUPLICATE_LOOKBACK_DAYS, SUBSCRIPTION_LOOKBACK_DAYS, TRIAL_LOOKBACK_DAYS, GRAY_CHARGE_LOOKBACK_DAYS
    )
    since = today - timedelta(days=lookback_days)

    with get_session() as session:
        txns = (
            session.query(TransactionRow)
            .filter(
                TransactionRow.date >= since,
                TransactionRow.is_pending.is_(False),
                TransactionRow.merchant_name.isnot(None),
            )
            .all()
        )
        if not txns:
            logger.info("[charge_guardian] No transactions in lookback window — skipping")
            return

        # Exclude investment activity (Schwab stock/ETF orders land in the main
        # transactions table with category="Investment Transfer" and the ticker as
        # merchant_name). Without this the duplicate detector treats same-symbol
        # trades within the window as duplicate charges (finforge-26). None-safe:
        # a real spending row never has this category.
        debit_txns = [
            t
            for t in txns
            if t.amount is not None
            and t.amount > 0
            and t.category != "Investment Transfer"
        ]

        recurring_merchants = find_recurring_merchants(
            [t for t in debit_txns if t.date >= today - timedelta(days=SUBSCRIPTION_LOOKBACK_DAYS)]
        )

        all_findings: list[Finding] = []
        all_findings += detect_duplicate_charges(
            [t for t in debit_txns if t.date >= today - timedelta(days=DUPLICATE_LOOKBACK_DAYS)],
            recurring_merchants=recurring_merchants,
        )
        all_findings += detect_new_subscriptions(
            [t for t in debit_txns if t.date >= today - timedelta(days=SUBSCRIPTION_LOOKBACK_DAYS)]
        )
        all_findings += detect_trial_conversions(
            [t for t in debit_txns if t.date >= today - timedelta(days=TRIAL_LOOKBACK_DAYS)]
        )
        all_findings += detect_gray_charge_creep(
            [t for t in debit_txns if t.date >= today - timedelta(days=GRAY_CHARGE_LOOKBACK_DAYS)],
            today=today,
        )

        created_findings = _persist_findings(session, all_findings)

        now = datetime.now(timezone.utc)
        for f in created_findings:
            session.add(NotificationRow(
                id=uuid.uuid4(),
                source="charge_guardian",
                title=f.title,
                alert_type=f.kind,
                message=f.detail,
                is_acknowledged=False,
                acknowledged_at=None,
                created_at=now,
            ))

    logger.info("[charge_guardian] %d new finding(s) created", len(created_findings))

    if not created_findings:
        return

    try:
        from notify import queue_notification
        for f in created_findings:
            emoji = NOTIFICATION_EMOJI.get(f.kind, "🔎")
            queue_notification("charge_guardian", f"{emoji} {f.title}\n{f.detail}", priority="normal")
    except Exception:
        pass
