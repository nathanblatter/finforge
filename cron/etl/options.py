"""Option-contract helpers shared by the API and cron (cron/etl/options.py is
an identical copy — the two images don't share code; keep them in sync).

Schwab identifies listed options by their OCC symbol, e.g.
``"AAL   261023C0001550"``: a root padded to 6 chars, YYMMDD expiration,
C/P, and the strike x1000 as 8 digits. Everything else in FinForge (holdings,
investment_transactions, market cache) keys on that raw string, so these
helpers are the one place that knows how to read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

ASSET_EQUITY = "EQUITY"
ASSET_OPTION = "OPTION"
OPTION_MULTIPLIER = 100  # shares per standard contract

# Strike is 8 digits (dollars x1000). Rows synced before the symbol columns were
# widened past 20 chars lost the final digit; since real strikes never use the
# 0.001 place that digit is always "0", so a 7-digit strike decodes safely.
_OCC_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,5})\s*(\d{6})([CP])(\d{7,8})$")


@dataclass(frozen=True)
class OptionContract:
    underlying: str
    expiration: date
    put_call: str  # "CALL" | "PUT"
    strike: Decimal

    @property
    def display(self) -> str:
        """Human form: ``AAL 10/23/26 $15.50 Call``."""
        kind = "Call" if self.put_call == "CALL" else "Put"
        return f"{self.underlying} {self.expiration:%m/%d/%y} ${self.strike:.2f} {kind}"


def parse_occ_symbol(symbol: str | None) -> OptionContract | None:
    """Return the contract encoded by an OCC symbol, or None for anything else."""
    if not symbol:
        return None
    m = _OCC_RE.match(symbol.strip().upper())
    if not m:
        return None
    root, yymmdd, cp, strike_raw = m.groups()
    if len(strike_raw) == 7:
        strike_raw += "0"
    try:
        expiration = datetime.strptime(yymmdd, "%y%m%d").date()
    except ValueError:
        return None
    return OptionContract(
        underlying=root,
        expiration=expiration,
        put_call="CALL" if cp == "C" else "PUT",
        strike=(Decimal(strike_raw) / 1000).quantize(Decimal("0.01")),
    )


def is_option_symbol(symbol: str | None) -> bool:
    return parse_occ_symbol(symbol) is not None


def display_symbol(symbol: str) -> str:
    """OCC symbol → readable contract; plain tickers pass through untouched."""
    contract = parse_occ_symbol(symbol)
    return contract.display if contract else symbol
