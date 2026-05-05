"""Portfolio analysis endpoints — risk metrics, rebalancing, tax-loss harvesting, drawdown predictions."""

import logging
import uuid
from datetime import date
from decimal import Decimal

import httpx
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db
from models.db_models import Account, DrawdownPrediction, Holding, PortfolioAnalysis, PortfolioTarget
from schemas.schemas import (
    DrawdownPredictionRequest,
    DrawdownPredictionResponse,
    PortfolioAnalysisResponse,
    PortfolioDrawdownResponse,
    PortfolioMetrics,
    PortfolioTargetItem,
    PortfolioTargetsRequest,
    RebalanceAction,
    SymbolAnalysis,
    TLHCandidate,
)
from services.drawdown_features import compute_features, load_model
from services.schwab import get_access_token, schwab_api_get

logger = logging.getLogger("finforge.portfolio_analysis")

router = APIRouter(prefix="/portfolio", tags=["portfolio-analysis"])

PORTFOLIO_SENTINEL = "__PORTFOLIO__"


def _get_brokerage(db: Session) -> Account:
    acct = db.query(Account).filter(Account.alias == "Schwab Brokerage", Account.is_active.is_(True)).first()
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active brokerage account")
    return acct


@router.get("/analysis", response_model=PortfolioAnalysisResponse)
def get_analysis(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    acct = _get_brokerage(db)

    # Get latest analysis date
    latest_date = (
        db.query(PortfolioAnalysis.analysis_date)
        .filter(PortfolioAnalysis.account_id == acct.id)
        .order_by(desc(PortfolioAnalysis.analysis_date))
        .first()
    )
    if not latest_date:
        return PortfolioAnalysisResponse(
            portfolio_metrics=PortfolioMetrics(),
            holdings=[],
            rebalance_actions=[],
            tlh_candidates=[],
        )

    analysis_date = latest_date[0]
    rows = (
        db.query(PortfolioAnalysis)
        .filter(PortfolioAnalysis.account_id == acct.id, PortfolioAnalysis.analysis_date == analysis_date)
        .all()
    )

    # Separate sentinel from per-symbol
    sentinel = None
    symbol_rows = []
    for r in rows:
        if r.symbol == PORTFOLIO_SENTINEL:
            sentinel = r
        else:
            symbol_rows.append(r)

    # Portfolio metrics
    metrics = PortfolioMetrics(
        hhi=sentinel.hhi if sentinel else None,
        top5_concentration=sentinel.top5_concentration if sentinel else None,
        weighted_volatility=sentinel.weighted_volatility if sentinel else None,
        max_drawdown=sentinel.max_drawdown if sentinel else None,
    )

    # Holdings
    holdings = []
    for r in symbol_rows:
        holdings.append(SymbolAnalysis(
            symbol=r.symbol,
            market_value=r.market_value,
            cost_basis=r.cost_basis,
            unrealized_gl=r.unrealized_gl,
            pct_of_portfolio=r.pct_of_portfolio,
            target_pct=r.target_pct,
            drift_pct=r.drift_pct,
            annualized_vol=r.annualized_vol,
            beta=r.beta,
            drawdown_from_high=r.drawdown_from_high,
            tlh_candidate=r.tlh_candidate,
            wash_sale_risk=r.wash_sale_risk,
            wash_sale_details=r.wash_sale_details,
        ))

    # Compute total portfolio value for rebalance trade suggestions
    total_value = sum(float(r.market_value or 0) for r in symbol_rows)

    # Rebalance actions (only for symbols with targets)
    rebalance = []
    for r in symbol_rows:
        if r.target_pct is not None and r.drift_pct is not None:
            drift = float(r.drift_pct)
            if abs(drift) < 1.0:
                action = "HOLD"
            elif drift > 0:
                action = "SELL"
            else:
                action = "BUY"
            trade_val = abs(drift / 100) * total_value
            rebalance.append(RebalanceAction(
                symbol=r.symbol,
                current_pct=r.pct_of_portfolio or Decimal("0"),
                target_pct=r.target_pct,
                drift_pct=r.drift_pct,
                action=action,
                suggested_trade_value=Decimal(str(round(trade_val, 2))),
            ))

    # TLH candidates
    tlh = []
    for r in symbol_rows:
        if r.tlh_candidate and r.unrealized_gl is not None and r.cost_basis is not None:
            tlh.append(TLHCandidate(
                symbol=r.symbol,
                unrealized_gl=r.unrealized_gl,
                market_value=r.market_value or Decimal("0"),
                cost_basis=r.cost_basis,
                wash_sale_risk=r.wash_sale_risk,
                wash_sale_details=r.wash_sale_details,
            ))

    return PortfolioAnalysisResponse(
        analysis_date=analysis_date,
        portfolio_metrics=metrics,
        holdings=holdings,
        rebalance_actions=rebalance,
        tlh_candidates=tlh,
    )


@router.get("/targets")
def get_targets(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    acct = _get_brokerage(db)
    rows = db.query(PortfolioTarget).filter(PortfolioTarget.account_id == acct.id).all()
    return {
        "targets": [
            {"symbol": r.symbol, "target_pct": r.target_pct}
            for r in rows
        ]
    }


@router.put("/targets")
def set_targets(
    body: PortfolioTargetsRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    acct = db.query(Account).filter(Account.alias == body.account_alias, Account.is_active.is_(True)).first()
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account '{body.account_alias}' not found")

    total = sum(float(t.target_pct) for t in body.targets)
    if total > 100:
        raise HTTPException(status_code=400, detail=f"Target allocations sum to {total}%, must be <= 100%")

    # Replace all targets
    db.query(PortfolioTarget).filter(PortfolioTarget.account_id == acct.id).delete()
    for t in body.targets:
        db.add(PortfolioTarget(
            account_id=acct.id,
            symbol=t.symbol.upper().strip(),
            target_pct=t.target_pct,
        ))
    db.commit()

    return {"targets": [{"symbol": t.symbol.upper().strip(), "target_pct": t.target_pct} for t in body.targets]}


@router.delete("/targets/{symbol}", status_code=204)
def delete_target(
    symbol: str,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    acct = _get_brokerage(db)
    row = db.query(PortfolioTarget).filter(
        PortfolioTarget.account_id == acct.id,
        PortfolioTarget.symbol == symbol.upper(),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Drawdown predictions
# ---------------------------------------------------------------------------

def _risk_level(prob: float) -> str:
    if prob < 0.20:
        return "LOW"
    if prob < 0.40:
        return "MODERATE"
    if prob < 0.60:
        return "HIGH"
    return "VERY_HIGH"


async def _predict_symbol(symbol: str, model, meta: dict) -> dict:
    """Fetch data and run inference for a single symbol."""
    symbol = symbol.upper().strip()

    # Fetch price history
    data = await schwab_api_get(
        "/pricehistory",
        params={"symbol": symbol, "periodType": "year", "period": 1,
                "frequencyType": "daily", "frequency": 1},
        market_data=True,
    )
    candles = data.get("candles", [])
    if len(candles) < 60:
        raise HTTPException(status_code=400, detail=f"Insufficient price history for {symbol}")

    closes = np.array([c["close"] for c in candles], dtype=float)
    volumes = np.array([c.get("volume", 0) for c in candles], dtype=float)

    # Fetch quote for fundamentals
    quote_data = await schwab_api_get(
        "/quotes",
        params={"symbols": symbol, "fields": "quote,fundamental"},
        market_data=True,
    )
    qi = quote_data.get(symbol, {})
    q = qi.get("quote", {})
    f = qi.get("fundamental", {})

    features = compute_features(
        closes, volumes,
        high_52w=q.get("52WkHigh"),
        pe_ratio=f.get("peRatio"),
        dividend_yield=f.get("divYield"),
    )

    if len(features) == 0 or np.isnan(features[-1]).any():
        raise HTTPException(status_code=400, detail=f"Could not compute features for {symbol}")

    latest_features = features[-1:].copy()
    # Replace any remaining NaN with 0
    latest_features = np.nan_to_num(latest_features, nan=0.0)

    prob = float(model.predict_proba(latest_features)[0, 1])

    return {
        "symbol": symbol,
        "drawdown_probability": round(prob, 4),
        "risk_level": _risk_level(prob),
        "model_version": meta.get("trained_at", "unknown"),
        "model_auc": meta.get("val_auc"),
    }


@router.post("/predict", response_model=DrawdownPredictionResponse)
async def predict_drawdown(
    body: DrawdownPredictionRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """On-demand drawdown prediction for any symbol."""
    model, meta = load_model()
    if model is None:
        raise HTTPException(status_code=503, detail="Model not trained yet. Run 'Drawdown Model Training' from Settings.")

    try:
        result = await _predict_symbol(body.symbol, model, meta)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Prediction failed for %s", body.symbol)
        raise HTTPException(status_code=502, detail=str(exc))

    today = date.today()

    # Cache prediction
    existing = db.query(DrawdownPrediction).filter_by(symbol=result["symbol"], prediction_date=today).first()
    if existing:
        existing.drawdown_probability = result["drawdown_probability"]
        existing.model_version = result["model_version"]
    else:
        db.add(DrawdownPrediction(
            id=uuid.uuid4(),
            symbol=result["symbol"],
            prediction_date=today,
            drawdown_probability=result["drawdown_probability"],
            model_version=result["model_version"],
        ))
    db.commit()

    return DrawdownPredictionResponse(
        prediction_date=today,
        **result,
    )


@router.get("/predictions", response_model=PortfolioDrawdownResponse)
def get_predictions(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    """Return cached predictions for held symbols."""
    _, meta = load_model()

    acct = _get_brokerage(db)

    # Get held symbols from latest snapshot
    from sqlalchemy import func as sqlfunc
    latest_date = db.query(sqlfunc.max(Holding.snapshot_date)).filter(Holding.account_id == acct.id).scalar()
    if not latest_date:
        return PortfolioDrawdownResponse(predictions=[], model_trained_at=meta.get("trained_at") if meta else None)

    held_symbols = [
        r[0] for r in
        db.query(Holding.symbol).filter(Holding.account_id == acct.id, Holding.snapshot_date == latest_date).distinct().all()
    ]

    # Get cached predictions for today
    today = date.today()
    rows = (
        db.query(DrawdownPrediction)
        .filter(DrawdownPrediction.symbol.in_(held_symbols), DrawdownPrediction.prediction_date == today)
        .all()
    )

    predictions = [
        DrawdownPredictionResponse(
            symbol=r.symbol,
            drawdown_probability=r.drawdown_probability,
            risk_level=_risk_level(float(r.drawdown_probability)),
            prediction_date=r.prediction_date,
            model_version=r.model_version,
            model_auc=Decimal(str(meta.get("val_auc", 0))) if meta else None,
        )
        for r in rows
    ]

    return PortfolioDrawdownResponse(
        predictions=predictions,
        model_trained_at=meta.get("trained_at") if meta else None,
        model_auc=Decimal(str(meta.get("val_auc", 0))) if meta else None,
    )
