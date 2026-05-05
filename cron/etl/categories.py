"""
Plaid personal_finance_category → FinForge internal category mapping.

Plaid v2 returns personal_finance_category as a dict:
  {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANTS", ...}

FinForge buckets:
  Food & Drink     — Restaurants, Coffee, Groceries
  Shopping         — Clothing, Electronics, General Retail
  Transport        — Gas, Rideshare, Parking
  Entertainment    — Subscriptions, Events
  Health           — Gym, Medical, Pharmacy
  Housing          — Rent, Utilities
  Education        — Tuition, Fees
  Investment Transfer — savings activity (tracked separately)
  Other            — uncategorized
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plaid v2 personal_finance_category.primary → (FinForge category, subcategory)
# ---------------------------------------------------------------------------

_PFC_PRIMARY_MAP: dict[str, tuple[str, str]] = {
    "FOOD_AND_DRINK": ("Food & Drink", "Restaurants"),
    "GROCERIES": ("Food & Drink", "Groceries"),
    "SHOPPING": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE": ("Shopping", "General Retail"),
    "TRANSPORTATION": ("Transport", "Rideshare"),
    "TRAVEL": ("Transport", "Rideshare"),
    "ENTERTAINMENT": ("Entertainment", "Events"),
    "PERSONAL_CARE": ("Health", "Medical"),
    "MEDICAL": ("Health", "Medical"),
    "RENT_AND_UTILITIES": ("Housing", "Rent"),
    "HOME_IMPROVEMENT": ("Housing", "Rent"),
    "EDUCATION": ("Education", "Fees"),
    "TRANSFER_IN": ("Investment Transfer", ""),
    "TRANSFER_OUT": ("Investment Transfer", ""),
    "LOAN_PAYMENTS": ("Investment Transfer", ""),
    "BANK_FEES": ("Other", ""),
    "INCOME": ("Other", ""),
    "GOVERNMENT_AND_NON_PROFIT": ("Other", ""),
    "OTHER": ("Other", ""),
}

# ---------------------------------------------------------------------------
# Plaid v2 detailed → more specific subcategory overrides
# ---------------------------------------------------------------------------

_PFC_DETAILED_MAP: dict[str, tuple[str, str]] = {
    # Food & Drink
    "FOOD_AND_DRINK_RESTAURANTS": ("Food & Drink", "Restaurants"),
    "FOOD_AND_DRINK_COFFEE": ("Food & Drink", "Coffee"),
    "FOOD_AND_DRINK_FAST_FOOD": ("Food & Drink", "Restaurants"),
    "FOOD_AND_DRINK_GROCERIES": ("Food & Drink", "Groceries"),
    "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR": ("Food & Drink", "Restaurants"),
    "FOOD_AND_DRINK_VENDING_MACHINES": ("Food & Drink", "Restaurants"),

    # Shopping
    "SHOPPING_CLOTHING_AND_ACCESSORIES": ("Shopping", "Clothing"),
    "SHOPPING_ELECTRONICS": ("Shopping", "Electronics"),
    "GENERAL_MERCHANDISE_DEPARTMENT_STORES": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE_SUPERSTORES": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE_SPORTING_GOODS": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS": ("Shopping", "General Retail"),
    "GENERAL_MERCHANDISE_PHARMACIES": ("Health", "Pharmacy"),

    # Transport
    "TRANSPORTATION_GAS": ("Transport", "Gas"),
    "TRANSPORTATION_PARKING": ("Transport", "Parking"),
    "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": ("Transport", "Rideshare"),
    "TRANSPORTATION_PUBLIC_TRANSIT": ("Transport", "Rideshare"),
    "TRANSPORTATION_TOLLS": ("Transport", "Parking"),
    "TRAVEL_FLIGHTS": ("Transport", "Rideshare"),
    "TRAVEL_LODGING": ("Entertainment", "Events"),
    "TRAVEL_RENTAL_CARS": ("Transport", "Rideshare"),

    # Entertainment
    "ENTERTAINMENT_MUSIC_AND_AUDIO": ("Entertainment", "Subscriptions"),
    "ENTERTAINMENT_TV_AND_MOVIES": ("Entertainment", "Subscriptions"),
    "ENTERTAINMENT_VIDEO_GAMES": ("Entertainment", "Subscriptions"),
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": ("Entertainment", "Events"),
    "ENTERTAINMENT_CASINOS_AND_GAMBLING": ("Entertainment", "Events"),

    # Health
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": ("Health", "Pharmacy"),
    "MEDICAL_DENTIST_AND_OPTOMETRIST": ("Health", "Medical"),
    "MEDICAL_VETERINARY_SERVICES": ("Health", "Medical"),
    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": ("Health", "Gym"),
    "PERSONAL_CARE_HAIR_AND_BEAUTY": ("Health", "Medical"),

    # Housing
    "RENT_AND_UTILITIES_RENT": ("Housing", "Rent"),
    "RENT_AND_UTILITIES_ELECTRICITY": ("Housing", "Rent"),
    "RENT_AND_UTILITIES_GAS": ("Housing", "Rent"),
    "RENT_AND_UTILITIES_WATER": ("Housing", "Rent"),
    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": ("Entertainment", "Subscriptions"),
    "RENT_AND_UTILITIES_TELEPHONE": ("Entertainment", "Subscriptions"),

    # Education
    "EDUCATION_TUITION_AND_FEES": ("Education", "Tuition"),
    "EDUCATION_STUDENT_LOAN": ("Education", "Fees"),
}

# ---------------------------------------------------------------------------
# Legacy Plaid category list → (FinForge category, subcategory)
# Kept as fallback for any transactions that still use the old format.
# ---------------------------------------------------------------------------

_LEGACY_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "Food and Drink": ("Food & Drink", "Restaurants"),
    "Shops": ("Shopping", "General Retail"),
    "Travel": ("Transport", "Rideshare"),
    "Recreation": ("Entertainment", "Events"),
    "Service": ("Other", ""),
    "Service|Subscription": ("Entertainment", "Subscriptions"),
    "Healthcare": ("Health", "Medical"),
    "Education": ("Education", "Fees"),
    "Transfer": ("Investment Transfer", ""),
    "Payment": ("Investment Transfer", ""),
    "Bank Fees": ("Other", ""),
}


def map_category(
    plaid_category: list[str] | None,
    personal_finance_category: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Map Plaid category data to (finforge_category, finforge_subcategory).

    Prefers the v2 personal_finance_category if available, falls back to
    the legacy category list.
    """
    # Try v2 personal_finance_category first
    if personal_finance_category:
        detailed = personal_finance_category.get("detailed", "")
        primary = personal_finance_category.get("primary", "")

        # Try detailed key first
        if detailed and detailed in _PFC_DETAILED_MAP:
            return _PFC_DETAILED_MAP[detailed]

        # Fall back to primary key
        if primary and primary in _PFC_PRIMARY_MAP:
            return _PFC_PRIMARY_MAP[primary]

    # Fall back to legacy category list
    if plaid_category:
        primary = plaid_category[0] if len(plaid_category) > 0 else ""
        secondary = plaid_category[1] if len(plaid_category) > 1 else ""

        if secondary:
            compound = f"{primary}|{secondary}"
            if compound in _LEGACY_CATEGORY_MAP:
                return _LEGACY_CATEGORY_MAP[compound]

        if primary in _LEGACY_CATEGORY_MAP:
            return _LEGACY_CATEGORY_MAP[primary]

    logger.debug(
        "No category mapping for pfc=%r legacy=%r — defaulting to Other",
        personal_finance_category, plaid_category,
    )
    return ("Other", "")
