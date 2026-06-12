"""
Static sector classification data for the exposure breakdown.

Schwab's market data API does not expose sector or ETF composition, so this
module carries approximate, hand-maintained mappings:

  - STOCK_SECTORS: GICS-style sector for common individual tickers
  - ETF_SECTOR_WEIGHTS: approximate sector weights for popular broad ETFs
    (compositions drift slowly; these are indicative, not exact)

Anything unmapped lands in "Unclassified" so the UI can be honest about
coverage.
"""

STOCK_SECTORS: dict[str, str] = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AVGO": "Technology", "ADBE": "Technology", "CRM": "Technology",
    "AMD": "Technology", "INTC": "Technology", "QCOM": "Technology",
    "TXN": "Technology", "ORCL": "Technology", "CSCO": "Technology",
    "IBM": "Technology", "NOW": "Technology", "PLTR": "Technology",
    "SNOW": "Technology", "PANW": "Technology", "MU": "Technology",
    "TSM": "Technology", "ASML": "Technology",
    # Communication Services
    "GOOGL": "Communication Services", "GOOG": "Communication Services",
    "META": "Communication Services", "NFLX": "Communication Services",
    "DIS": "Communication Services", "T": "Communication Services",
    "VZ": "Communication Services", "CMCSA": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    # Consumer Staples
    "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "COST": "Consumer Staples", "CL": "Consumer Staples",
    # Financials
    "JPM": "Financials", "V": "Financials", "MA": "Financials",
    "BAC": "Financials", "GS": "Financials", "AXP": "Financials",
    "WFC": "Financials", "MS": "Financials", "BRK.B": "Financials",
    "SCHW": "Financials", "BLK": "Financials", "C": "Financials",
    # Health Care
    "JNJ": "Health Care", "UNH": "Health Care", "PFE": "Health Care",
    "MRK": "Health Care", "LLY": "Health Care", "ABT": "Health Care",
    "TMO": "Health Care", "ABBV": "Health Care", "AMGN": "Health Care",
    "ISRG": "Health Care", "CVS": "Health Care",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    # Industrials
    "CAT": "Industrials", "DE": "Industrials", "RTX": "Industrials",
    "BA": "Industrials", "HON": "Industrials", "UPS": "Industrials",
    "GE": "Industrials", "LMT": "Industrials", "UNP": "Industrials",
    # Utilities / Real Estate / Materials
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "PLD": "Real Estate", "AMT": "Real Estate", "O": "Real Estate",
    "LIN": "Materials", "SHW": "Materials", "FCX": "Materials",
}

# Approximate sector weights for popular ETFs. Values sum to ~1.0.
ETF_SECTOR_WEIGHTS: dict[str, dict[str, float]] = {
    # S&P 500 trackers
    "SPY": {
        "Technology": 0.31, "Financials": 0.13, "Health Care": 0.12,
        "Consumer Discretionary": 0.10, "Communication Services": 0.09,
        "Industrials": 0.08, "Consumer Staples": 0.06, "Energy": 0.04,
        "Utilities": 0.025, "Real Estate": 0.022, "Materials": 0.023,
    },
    "QQQ": {
        "Technology": 0.51, "Communication Services": 0.15,
        "Consumer Discretionary": 0.13, "Health Care": 0.06,
        "Consumer Staples": 0.06, "Industrials": 0.05,
        "Utilities": 0.01, "Financials": 0.01, "Energy": 0.01, "Materials": 0.01,
    },
    "VTI": {
        "Technology": 0.30, "Financials": 0.14, "Health Care": 0.12,
        "Consumer Discretionary": 0.10, "Communication Services": 0.08,
        "Industrials": 0.09, "Consumer Staples": 0.055, "Energy": 0.04,
        "Utilities": 0.025, "Real Estate": 0.03, "Materials": 0.025,
    },
    "IWM": {
        "Financials": 0.18, "Industrials": 0.17, "Health Care": 0.15,
        "Technology": 0.14, "Consumer Discretionary": 0.10, "Energy": 0.06,
        "Real Estate": 0.06, "Consumer Staples": 0.03, "Materials": 0.04,
        "Utilities": 0.03, "Communication Services": 0.03,
    },
    "DIA": {
        "Financials": 0.21, "Technology": 0.20, "Health Care": 0.15,
        "Consumer Discretionary": 0.14, "Industrials": 0.13,
        "Consumer Staples": 0.07, "Communication Services": 0.04,
        "Energy": 0.03, "Materials": 0.02, "Utilities": 0.01,
    },
    "SCHD": {
        "Financials": 0.18, "Health Care": 0.15, "Consumer Staples": 0.14,
        "Industrials": 0.13, "Energy": 0.12, "Consumer Discretionary": 0.10,
        "Technology": 0.09, "Communication Services": 0.05, "Materials": 0.04,
    },
    "VIG": {
        "Technology": 0.24, "Financials": 0.18, "Health Care": 0.15,
        "Industrials": 0.12, "Consumer Staples": 0.11,
        "Consumer Discretionary": 0.08, "Utilities": 0.04,
        "Materials": 0.04, "Communication Services": 0.02, "Energy": 0.02,
    },
    # International — bucketed as a single exposure
    "VXUS": {"International Equity": 1.0},
    "VEA": {"International Equity": 1.0},
    "VWO": {"International Equity": 1.0},
    "IXUS": {"International Equity": 1.0},
    "EFA": {"International Equity": 1.0},
    # Fixed income
    "BND": {"Bonds": 1.0},
    "AGG": {"Bonds": 1.0},
    "TLT": {"Bonds": 1.0},
    "SHY": {"Bonds": 1.0},
    "BNDX": {"Bonds": 1.0},
}

# VOO and IVV mirror SPY
ETF_SECTOR_WEIGHTS["VOO"] = ETF_SECTOR_WEIGHTS["SPY"]
ETF_SECTOR_WEIGHTS["IVV"] = ETF_SECTOR_WEIGHTS["SPY"]

MONEY_MARKET_SECTORS = {"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"}


def classify_holding(symbol: str, market_value: float) -> dict[str, float]:
    """Return {sector: dollar exposure} for one holding."""
    symbol = symbol.upper()
    if symbol in MONEY_MARKET_SECTORS:
        return {"Cash": market_value}
    if symbol in ETF_SECTOR_WEIGHTS:
        return {sector: market_value * w for sector, w in ETF_SECTOR_WEIGHTS[symbol].items()}
    if symbol in STOCK_SECTORS:
        return {STOCK_SECTORS[symbol]: market_value}
    return {"Unclassified": market_value}
