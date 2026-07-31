"""FIRE / retirement projector — years-to-FI, Coast-FIRE, and safe-withdrawal
stress testing, built on top of the wave-4 quant suite (services.quant):
the same block-bootstrap Monte Carlo engine that powers /quant/montecarlo
drives both the years-to-FI distribution and the decumulation stress test
here, pointed at the user's real current allocation across every linked
brokerage/IRA account (services.fire.invested_weights) rather than a single
hardcoded account or generic asset-class assumptions.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db
from models.db_models import FireSettings
from services import fire

logger = logging.getLogger("finforge.fire")

router = APIRouter(prefix="/fire", tags=["fire"])


# ---------------------------------------------------------------------------
# Settings (persisted, singleton row — single-user app)
# ---------------------------------------------------------------------------

class FireSettingsUpdate(BaseModel):
    current_age: Optional[int] = Field(default=None, ge=0, le=120)
    target_retirement_age: Optional[int] = Field(default=None, ge=1, le=120)
    expected_annual_spend: Optional[float] = Field(default=None, ge=0)
    withdrawal_rate: Optional[float] = Field(default=None, gt=0, le=0.20)


def _settings_dict(row: FireSettings) -> dict:
    return {
        "current_age": row.current_age,
        "target_retirement_age": row.target_retirement_age,
        "expected_annual_spend": float(row.expected_annual_spend) if row.expected_annual_spend is not None else None,
        "withdrawal_rate": float(row.withdrawal_rate),
    }


def _get_or_create_settings(db: Session) -> FireSettings:
    row = db.query(FireSettings).order_by(FireSettings.created_at).first()
    if row is None:
        row = FireSettings()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    return _settings_dict(_get_or_create_settings(db))


@router.put("/settings")
def update_settings(
    body: FireSettingsUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    row = _get_or_create_settings(db)
    if body.current_age is not None:
        row.current_age = body.current_age
    if body.target_retirement_age is not None:
        row.target_retirement_age = body.target_retirement_age
    if body.expected_annual_spend is not None:
        row.expected_annual_spend = body.expected_annual_spend
    if body.withdrawal_rate is not None:
        row.withdrawal_rate = body.withdrawal_rate
    db.commit()
    db.refresh(row)
    return _settings_dict(row)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resolve_annual_spend(db: Session, settings_row: FireSettings) -> float:
    """User-set expected retirement spend, or fall back to current
    annualized spend (income - savings) from trailing-12mo transactions."""
    if settings_row.expected_annual_spend is not None:
        return float(settings_row.expected_annual_spend)
    savings = fire.compute_savings_rate(db, months=12)
    return savings["expenses_annualized"]


# ---------------------------------------------------------------------------
# Summary — net worth, savings rate, FI number, deterministic years-to-FI,
# Coast-FIRE
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_summary(db: Session = Depends(get_db), _: dict = Depends(require_auth)):
    settings_row = _get_or_create_settings(db)

    try:
        net_worth = fire.compute_net_worth(db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    savings = fire.compute_savings_rate(db, months=12)

    annual_spend = _resolve_annual_spend(db, settings_row)
    withdrawal_rate = float(settings_row.withdrawal_rate)
    target = fire.fi_number(annual_spend, withdrawal_rate)

    try:
        weights, invested_total = fire.invested_weights(db)
    except ValueError:
        weights, invested_total = {}, net_worth["invested_assets"]

    # Deterministic growth rate: prefer the real portfolio's historical mean
    # return; fall back to the quant module's risk-free rate if we don't
    # have enough price history to compute one (e.g. no holdings yet).
    expected_return = None
    try:
        import asyncio
        portfolio_returns, _symbols, _w, _total = asyncio.run(fire.portfolio_return_series(db))
        expected_return = fire.expected_annual_return(portfolio_returns)
    except Exception as exc:
        logger.info("[fire] Falling back to risk-free rate for deterministic projection: %s", exc)

    from services.quant import RISK_FREE_RATE
    r = expected_return if expected_return is not None else RISK_FREE_RATE

    current_invested = net_worth["invested_assets"]
    annual_contribution = max(savings["annual_savings"], 0.0)

    years_to_fi = fire.years_to_fi_deterministic(current_invested, annual_contribution, r, target)

    current_age = settings_row.current_age
    target_age = settings_row.target_retirement_age
    coast_number = None
    coast_progress_pct = None
    coast_reached_age = None
    if current_age is not None and target_age is not None and target_age > current_age:
        years_until_retirement = target_age - current_age
        coast_number = fire.coast_fire_number(target, r, years_until_retirement)
        coast_progress_pct = round(current_invested / coast_number * 100, 2) if coast_number > 0 else None
        coast_reached_age = fire.coast_age(
            current_invested, annual_contribution, r, current_age, target_age, target,
        )

    return {
        "net_worth": net_worth,
        "savings": savings,
        "expected_annual_return": round(r, 4),
        "annual_retirement_spend": round(annual_spend, 2),
        "withdrawal_rate": withdrawal_rate,
        "fi_number": round(target, 2),
        "current_invested_assets": round(current_invested, 2),
        "years_to_fi": round(years_to_fi, 2) if years_to_fi is not None else None,
        "coast": {
            "current_age": current_age,
            "target_retirement_age": target_age,
            "coast_number": round(coast_number, 2) if coast_number is not None else None,
            "progress_pct": coast_progress_pct,
            "coast_reached_age": coast_reached_age,
        },
        "allocation_symbols": sorted(weights.keys()),
    }


# ---------------------------------------------------------------------------
# Monte Carlo years-to-FI (real allocation)
# ---------------------------------------------------------------------------

class FireMonteCarloRequest(BaseModel):
    max_years: int = Field(default=50, ge=5, le=60)
    n_sims: int = Field(default=2000, ge=500, le=5000)
    seed: Optional[int] = None


@router.post("/montecarlo")
async def run_fire_monte_carlo(
    body: FireMonteCarloRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    settings_row = _get_or_create_settings(db)
    try:
        portfolio_returns, symbols, weights, _total = await fire.portfolio_return_series(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    net_worth = fire.compute_net_worth(db)
    savings = fire.compute_savings_rate(db, months=12)
    annual_spend = _resolve_annual_spend(db, settings_row)
    withdrawal_rate = float(settings_row.withdrawal_rate)
    target = fire.fi_number(annual_spend, withdrawal_rate)
    annual_contribution = max(savings["annual_savings"], 0.0)

    try:
        result = fire.simulate_years_to_fi(
            portfolio_returns,
            initial_value=net_worth["invested_assets"],
            annual_contribution=annual_contribution,
            target_value=target,
            max_years=body.max_years,
            n_sims=body.n_sims,
            seed=body.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result["symbols"] = symbols
    result["fi_number"] = round(target, 2)
    return result


# ---------------------------------------------------------------------------
# Safe-withdrawal-rate stress test (decumulation)
# ---------------------------------------------------------------------------

class SwrRequest(BaseModel):
    rates: Optional[list[float]] = Field(default=None, description="Defaults to 3.0-4.5% in 0.5% steps")
    horizons: Optional[list[int]] = Field(default=None, description="Defaults to [30, 40, 50] years")
    n_sims: int = Field(default=1500, ge=500, le=5000)
    seed: Optional[int] = None


@router.post("/swr")
async def run_swr_stress_test(
    body: SwrRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    try:
        portfolio_returns, symbols, _weights, _total = await fire.portfolio_return_series(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    net_worth = fire.compute_net_worth(db)
    rates = body.rates or fire.SWR_RATES
    horizons = body.horizons or fire.SWR_HORIZONS

    result = fire.swr_table(
        portfolio_returns,
        initial_value=net_worth["invested_assets"],
        rates=rates,
        horizons=horizons,
        n_sims=body.n_sims,
        seed=body.seed,
    )
    result["symbols"] = symbols
    return result
