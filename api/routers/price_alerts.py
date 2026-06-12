"""Price alert endpoints — one-shot symbol threshold alerts checked by cron."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import verify_api_key
from models.db_models import MarketDataCache, PriceAlert
from schemas.schemas import (
    PriceAlertCreateRequest,
    PriceAlertItem,
    PriceAlertsListResponse,
)

router = APIRouter(prefix="/price-alerts", tags=["price-alerts"])

VALID_DIRECTIONS = {"above", "below"}


def _to_item(alert: PriceAlert, last_price=None) -> PriceAlertItem:
    item = PriceAlertItem.model_validate(alert)
    item.last_price = last_price
    return item


@router.get("", response_model=PriceAlertsListResponse)
def list_price_alerts(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> PriceAlertsListResponse:
    """All price alerts, newest first, enriched with the latest cached price."""
    alerts = db.query(PriceAlert).order_by(desc(PriceAlert.created_at)).all()
    symbols = {a.symbol for a in alerts}
    price_map = {}
    if symbols:
        rows = db.query(MarketDataCache).filter(MarketDataCache.symbol.in_(symbols)).all()
        price_map = {r.symbol: r.last_price for r in rows}
    return PriceAlertsListResponse(
        alerts=[_to_item(a, price_map.get(a.symbol)) for a in alerts]
    )


@router.post("", response_model=PriceAlertItem, status_code=status.HTTP_201_CREATED)
def create_price_alert(
    body: PriceAlertCreateRequest,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> PriceAlertItem:
    """Create a one-shot price alert."""
    symbol = body.symbol.upper().strip()
    direction = body.direction.lower().strip()
    if not symbol:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Symbol is required")
    if direction not in VALID_DIRECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Direction must be 'above' or 'below'")
    if body.threshold <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Threshold must be positive")

    alert = PriceAlert(symbol=symbol, direction=direction, threshold=body.threshold, is_active=True)
    db.add(alert)
    db.commit()
    db.refresh(alert)

    cache = db.query(MarketDataCache).filter_by(symbol=symbol).first()
    return _to_item(alert, cache.last_price if cache else None)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> None:
    """Delete a price alert."""
    alert = db.query(PriceAlert).filter_by(id=alert_id).first()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price alert not found")
    db.delete(alert)
    db.commit()
