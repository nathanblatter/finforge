"""Watchlist management endpoints — user-scoped symbol watchlists with cached quotes."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from auth import require_auth
from database import get_db
from models.db_models import MarketDataCache, Watchlist, WatchlistItem
from schemas.schemas import (
    MarketQuote,
    WatchlistAddSymbolRequest,
    WatchlistCreateRequest,
    WatchlistItemSchema,
    WatchlistRenameRequest,
    WatchlistSchema,
    WatchlistsListResponse,
)

logger = logging.getLogger("finforge.watchlists")

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _get_user_id(payload: dict) -> uuid.UUID:
    return uuid.UUID(payload["sub"])


def _enrich_with_quotes(watchlist: Watchlist, db: Session) -> WatchlistSchema:
    """Build a WatchlistSchema with cached quotes attached to each item."""
    symbols = [item.symbol for item in watchlist.items]
    quote_map: dict[str, MarketQuote] = {}
    if symbols:
        cache_rows = db.query(MarketDataCache).filter(MarketDataCache.symbol.in_(symbols)).all()
        for row in cache_rows:
            quote_map[row.symbol] = MarketQuote.model_validate(row)

    items = []
    for item in watchlist.items:
        item_schema = WatchlistItemSchema.model_validate(item)
        item_schema.quote = quote_map.get(item.symbol)
        items.append(item_schema)

    schema = WatchlistSchema.model_validate(watchlist)
    schema.items = items
    return schema


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=WatchlistsListResponse)
def list_watchlists(
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    watchlists = (
        db.query(Watchlist)
        .options(joinedload(Watchlist.items))
        .filter(Watchlist.user_id == user_id)
        .order_by(Watchlist.created_at)
        .all()
    )
    enriched = [_enrich_with_quotes(wl, db) for wl in watchlists]
    return WatchlistsListResponse(watchlists=enriched, total=len(enriched))


@router.post("", response_model=WatchlistSchema, status_code=status.HTTP_201_CREATED)
def create_watchlist(
    body: WatchlistCreateRequest,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)

    existing = db.query(Watchlist).filter_by(user_id=user_id, name=body.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Watchlist with this name already exists")

    wl = Watchlist(user_id=user_id, name=body.name)
    db.add(wl)
    db.flush()

    for sym in body.symbols:
        item = WatchlistItem(watchlist_id=wl.id, symbol=sym.upper().strip())
        db.add(item)

    db.commit()
    db.refresh(wl)
    return _enrich_with_quotes(wl, db)


@router.get("/{watchlist_id}", response_model=WatchlistSchema)
def get_watchlist(
    watchlist_id: uuid.UUID,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    wl = (
        db.query(Watchlist)
        .options(joinedload(Watchlist.items))
        .filter(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
        .first()
    )
    if not wl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    return _enrich_with_quotes(wl, db)


@router.put("/{watchlist_id}", response_model=WatchlistSchema)
def rename_watchlist(
    watchlist_id: uuid.UUID,
    body: WatchlistRenameRequest,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.user_id == user_id).first()
    if not wl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")

    # Check name uniqueness
    clash = db.query(Watchlist).filter(
        Watchlist.user_id == user_id, Watchlist.name == body.name, Watchlist.id != watchlist_id
    ).first()
    if clash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Watchlist with this name already exists")

    wl.name = body.name
    db.commit()
    db.refresh(wl)
    return _enrich_with_quotes(wl, db)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    watchlist_id: uuid.UUID,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.user_id == user_id).first()
    if not wl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")
    db.delete(wl)
    db.commit()


@router.post("/{watchlist_id}/symbols", response_model=WatchlistSchema, status_code=status.HTTP_201_CREATED)
def add_symbol(
    watchlist_id: uuid.UUID,
    body: WatchlistAddSymbolRequest,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    wl = (
        db.query(Watchlist)
        .options(joinedload(Watchlist.items))
        .filter(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
        .first()
    )
    if not wl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")

    symbol = body.symbol.upper().strip()
    existing = db.query(WatchlistItem).filter_by(watchlist_id=watchlist_id, symbol=symbol).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{symbol} already in watchlist")

    item = WatchlistItem(watchlist_id=watchlist_id, symbol=symbol)
    db.add(item)
    db.commit()
    db.refresh(wl)
    return _enrich_with_quotes(wl, db)


@router.delete("/{watchlist_id}/symbols/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_symbol(
    watchlist_id: uuid.UUID,
    symbol: str,
    payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = _get_user_id(payload)
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.user_id == user_id).first()
    if not wl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")

    item = db.query(WatchlistItem).filter_by(watchlist_id=watchlist_id, symbol=symbol.upper()).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{symbol} not in watchlist")

    db.delete(item)
    db.commit()
