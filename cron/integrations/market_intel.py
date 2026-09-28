"""
Market intelligence for held positions — earnings dates and IV spikes.

For every held (non money-market) symbol:
  - Earnings: flags an upcoming earnings date within 7 days if Schwab's
    fundamental data exposes one (field availability varies by symbol).
  - IV spike: compares ~30-day ATM implied volatility from the options
    chain to 30-day realized volatility; a large premium usually means the
    options market expects an event (earnings, FDA, litigation, ...).

Flags are queued for the NateBot morning briefing. One notification per
day at most; the job dedups by checking it already notified today.
"""

import logging
from datetime import date, datetime, timezone

import httpx
import numpy as np

from config import settings
from etl.options import is_option_symbol
from db import AccountRow, HoldingRow, NatebotQueueRow, get_session
from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager
from sqlalchemy import func

logger = logging.getLogger("finforge.cron.market_intel")

SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"
MONEY_MARKET = frozenset({"SPAXX", "SWVXX", "VMFXX", "FDRXX", "SPRXX"})
IV_SPIKE_RATIO = 1.5      # IV must exceed 1.5x HV
IV_SPIKE_FLOOR = 0.35     # and be at least 35% absolute
EARNINGS_WINDOW_DAYS = 7
QUEUE_CATEGORY = "market_intel"

# Schwab fundamental field names that may carry an earnings date,
# depending on instrument type and API version.
EARNINGS_DATE_FIELDS = ("nextEarningsDate", "earningsDate", "nextEarningsDateTime")


def _held_symbols(session) -> list[str]:
    acct = session.query(AccountRow).filter(
        AccountRow.alias == "Schwab Brokerage", AccountRow.is_active.is_(True)
    ).first()
    if not acct:
        return []
    latest = session.query(func.max(HoldingRow.snapshot_date)).filter(
        HoldingRow.account_id == acct.id
    ).scalar()
    if not latest:
        return []
    rows = session.query(HoldingRow.symbol).filter(
        HoldingRow.account_id == acct.id, HoldingRow.snapshot_date == latest
    ).distinct().all()
    return sorted({r[0] for r in rows if r[0] and r[0] not in MONEY_MARKET and not is_option_symbol(r[0])})


def _already_notified_today(session) -> bool:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.query(NatebotQueueRow)
        .filter(
            NatebotQueueRow.category == QUEUE_CATEGORY,
            NatebotQueueRow.created_at >= today_start,
        )
        .first()
        is not None
    )


def _parse_earnings_date(fundamental: dict) -> date | None:
    for field in EARNINGS_DATE_FIELDS:
        raw = fundamental.get(field)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
    return None


def _hv_30d(closes: list[float]) -> float | None:
    if len(closes) < 31:
        return None
    arr = np.array(closes[-31:], dtype=float)
    rets = np.diff(arr) / arr[:-1]
    return float(np.std(rets, ddof=1) * np.sqrt(252))


def _atm_iv(chain: dict) -> float | None:
    vols_atm: list[float] = []
    vols_any: list[float] = []
    for map_key in ("callExpDateMap", "putExpDateMap"):
        for _exp, strikes in (chain.get(map_key) or {}).items():
            for _strike, contracts in strikes.items():
                for c in contracts:
                    dte = c.get("daysToExpiration")
                    vol = c.get("volatility")
                    delta = c.get("delta")
                    if dte is None or vol is None or vol <= 0 or vol > 500:
                        continue
                    if not (20 <= dte <= 45):
                        continue
                    vols_any.append(vol)
                    if delta is not None and 0.35 <= abs(delta) <= 0.65:
                        vols_atm.append(vol)
    pool = vols_atm or vols_any
    return (float(np.median(pool)) / 100.0) if pool else None


def run_market_intel() -> None:
    today = date.today()

    with get_session() as session:
        if _already_notified_today(session):
            logger.info("[market_intel] Already notified today — skipping")
            return
        symbols = _held_symbols(session)

    if not symbols:
        logger.info("[market_intel] No held symbols — skipping")
        return

    try:
        tm = SchwabTokenManager(
            token_file_path=settings.schwab_token_file,
            client_id=settings.schwab_client_id,
            client_secret=settings.schwab_client_secret,
        )
        tm.load_tokens()
        access_token = tm.get_valid_access_token()
    except SchwabReauthRequired:
        logger.critical("[market_intel] Schwab re-auth required — skipping")
        return
    except Exception as exc:
        logger.error("[market_intel] Token error: %s", exc)
        return

    earnings_flags: list[str] = []
    iv_flags: list[str] = []

    with httpx.Client(
        base_url=SCHWAB_MARKETDATA_BASE,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    ) as client:
        # Quotes (fundamentals) in one batch
        fundamentals: dict[str, dict] = {}
        try:
            resp = client.get("/quotes", params={"symbols": ",".join(symbols), "fields": "quote,fundamental"})
            if resp.is_success:
                for sym, info in resp.json().items():
                    fundamentals[sym] = info.get("fundamental", {}) or {}
        except Exception as exc:
            logger.warning("[market_intel] Quote batch failed: %s", exc)

        for sym in symbols:
            # Earnings within the window
            edate = _parse_earnings_date(fundamentals.get(sym, {}))
            if edate and 0 <= (edate - today).days <= EARNINGS_WINDOW_DAYS:
                earnings_flags.append(f"  {sym}: earnings {edate.strftime('%a %b %-d')}")

            # IV spike
            try:
                hist = client.get(
                    "/pricehistory",
                    params={"symbol": sym, "periodType": "year", "period": 1,
                            "frequencyType": "daily", "frequency": 1},
                )
                closes = [c["close"] for c in hist.json().get("candles", []) if c.get("close")] if hist.is_success else []
                hv = _hv_30d(closes)

                chain_resp = client.get(
                    "/chains",
                    params={"symbol": sym, "contractType": "ALL", "strikeCount": 6, "range": "NTM"},
                )
                iv = _atm_iv(chain_resp.json()) if chain_resp.is_success else None

                if hv and iv and hv > 0 and iv >= IV_SPIKE_FLOOR and iv / hv >= IV_SPIKE_RATIO:
                    iv_flags.append(
                        f"  {sym}: IV {iv*100:.0f}% vs HV {hv*100:.0f}% ({iv/hv:.1f}x) — options pricing an event"
                    )
            except Exception as exc:
                logger.debug("[market_intel] IV check failed for %s: %s", sym, exc)

    if not earnings_flags and not iv_flags:
        logger.info("[market_intel] No flags for %d held symbols", len(symbols))
        return

    lines = ["🗓 Position Watch"]
    if earnings_flags:
        lines.append("Earnings this week:")
        lines.extend(earnings_flags)
    if iv_flags:
        lines.append("Volatility spikes:")
        lines.extend(iv_flags)

    try:
        from notify import queue_notification
        queue_notification(QUEUE_CATEGORY, "\n".join(lines), priority="normal")
        logger.info(
            "[market_intel] Queued %d earnings + %d IV flag(s)",
            len(earnings_flags), len(iv_flags),
        )
    except Exception as exc:
        logger.error("[market_intel] Failed to queue notification: %s", exc)
