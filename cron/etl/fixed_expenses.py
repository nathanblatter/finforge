"""
Fixed expense detection for FinForge.

Fixed expenses (rent, tuition) are excluded from discretionary spend calculations.
Detection uses keyword matching on merchant name combined with amount thresholds
to reduce false positives.

PRD definition of fixed expenses:
  - Rent       — recurring, non-discretionary housing payment from WF Checking
  - Tuition    — recurring, non-discretionary education payment from WF Checking
  - Investment transfers — savings activity tracked separately, not discretionary
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rent detection
# ---------------------------------------------------------------------------

_RENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brent\b", re.IGNORECASE),
    re.compile(r"\bapartment\b", re.IGNORECASE),
    re.compile(r"\blease\b", re.IGNORECASE),
    re.compile(r"\bproperty management\b", re.IGNORECASE),
    re.compile(r"\blandlord\b", re.IGNORECASE),
    re.compile(r"\bhousing\b", re.IGNORECASE),
    # Common Zelle/Venmo patterns for rent payments
    re.compile(r"\bzelle.*rent\b", re.IGNORECASE),
    re.compile(r"\bvenmo.*rent\b", re.IGNORECASE),
    re.compile(r"\brent.*payment\b", re.IGNORECASE),
]

RENT_AMOUNT_MIN: float = 500.0  # only flag as rent if amount >= $500

# ---------------------------------------------------------------------------
# Tuition detection
# ---------------------------------------------------------------------------

_TUITION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\btuition\b", re.IGNORECASE),
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\bcollege\b", re.IGNORECASE),
    re.compile(r"\bstudent.*fee\b", re.IGNORECASE),
    re.compile(r"\bacademic.*fee\b", re.IGNORECASE),
    re.compile(r"\benrollment\b", re.IGNORECASE),
    re.compile(r"\bregistrar\b", re.IGNORECASE),
    re.compile(r"\bbursar\b", re.IGNORECASE),
    re.compile(r"\bfinancial aid\b", re.IGNORECASE),
    re.compile(r"\bstudent.*services\b", re.IGNORECASE),
    # Common school names — extend as needed
    re.compile(r"\bUCLA\b", re.IGNORECASE),
    re.compile(r"\bUSC\b"),
    re.compile(r"\bNYU\b"),
    re.compile(r"\bColumb(ia|us)\b", re.IGNORECASE),
]

TUITION_AMOUNT_MIN: float = 200.0  # only flag as tuition if amount >= $200


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def is_fixed_expense(
    merchant_name: str | None,
    amount: float,
    category: str | None,
) -> bool:
    """
    Return True if this transaction should be flagged as a fixed expense.

    Fixed expenses are excluded from discretionary spend calculations per PRD.
    Three paths to True:
      1. Merchant name matches rent keywords AND amount >= RENT_AMOUNT_MIN
      2. Merchant name matches tuition keywords AND amount >= TUITION_AMOUNT_MIN
      3. FinForge category is 'Investment Transfer'

    Args:
        merchant_name: Normalized merchant name string (may be None).
        amount: Transaction amount as a positive float (Plaid signs vary — use abs).
        category: FinForge internal category string (post-mapping).

    Returns:
        True if the transaction is a fixed / non-discretionary expense.
    """
    # Investment transfers are never discretionary spend
    if category == "Investment Transfer":
        return True

    name = (merchant_name or "").strip()
    abs_amount = abs(amount)

    # Rent check
    if abs_amount >= RENT_AMOUNT_MIN and _matches_any(name, _RENT_PATTERNS):
        logger.debug("Flagging as fixed expense (rent): %r amount=%.2f", name, abs_amount)
        return True

    # Tuition check
    if abs_amount >= TUITION_AMOUNT_MIN and _matches_any(name, _TUITION_PATTERNS):
        logger.debug("Flagging as fixed expense (tuition): %r amount=%.2f", name, abs_amount)
        return True

    return False


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    """Return True if text matches any of the compiled regex patterns."""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False
