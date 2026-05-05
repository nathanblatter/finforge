"""Schwab OAuth authentication endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from services.schwab import exchange_code, get_authorization_url

logger = logging.getLogger("finforge.schwab_auth")

router = APIRouter(prefix="/auth/schwab", tags=["schwab-auth"])


@router.get("/login")
async def schwab_login():
    """Redirect the user to Schwab's OAuth authorization page."""
    url = get_authorization_url()
    return RedirectResponse(url)


@router.get("/callback")
async def schwab_callback(
    code: str = Query(None),
    error: str = Query(None),
):
    """Handle the OAuth callback from Schwab."""
    if error:
        logger.error("Schwab OAuth error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Schwab OAuth error: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    try:
        tokens = await exchange_code(code)
        logger.info("Schwab OAuth completed successfully")
        return {
            "status": "ok",
            "message": "Schwab tokens saved successfully",
            "token_type": tokens.get("token_type"),
            "expires_in": tokens.get("expires_in"),
        }
    except Exception as exc:
        logger.exception("Failed to exchange Schwab auth code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange failed: {exc}",
        )
