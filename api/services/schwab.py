"""Schwab Trader API — OAuth token management and API client."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger("finforge.schwab")

_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_TRADER_BASE = "https://api.schwabapi.com/trader/v1"
SCHWAB_MARKETDATA_BASE = "https://api.schwabapi.com/marketdata/v1"


def get_authorization_url() -> str:
    """Build the Schwab OAuth authorization URL."""
    params = {
        "client_id": settings.schwab_client_id,
        "redirect_uri": settings.schwab_redirect_uri,
        "response_type": "code",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_AUTH_URL}?{qs}"


def _save_tokens(data: dict) -> None:
    """Persist tokens in the format expected by both API and cron."""
    # Compute expires_at from expires_in for cron compatibility
    expires_in = int(data.get("expires_in", 1800))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    data["expires_at"] = expires_at

    # Atomic write
    path = Path(settings.schwab_token_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = str(path) + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, str(path))
    logger.info("Schwab tokens saved to %s", path)


def _load_tokens() -> dict | None:
    """Load tokens from disk, or None if not present."""
    path = Path(settings.schwab_token_file)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _basic_auth() -> tuple[str, str]:
    return (settings.schwab_client_id, settings.schwab_client_secret)


def _is_expired(tokens: dict) -> bool:
    """Check if the access token is expired or within 60s of expiry."""
    expires_at_str = tokens.get("expires_at")
    if expires_at_str:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires_at - timedelta(seconds=60)
    return True  # No expiry info, assume expired


async def exchange_code(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.schwab_redirect_uri,
            },
            auth=_basic_auth(),
        )
        resp.raise_for_status()
        tokens = resp.json()
        _save_tokens(tokens)
        return tokens


async def refresh_access_token() -> dict:
    """Use the refresh token to get a new access token."""
    tokens = _load_tokens()
    if not tokens or "refresh_token" not in tokens:
        raise RuntimeError("No Schwab refresh token found — re-authorize via /api/v1/auth/schwab/login")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
            },
            auth=_basic_auth(),
        )
        resp.raise_for_status()
        new_tokens = resp.json()
        # Preserve existing fields (account_hashes, etc.)
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = tokens["refresh_token"]
        merged = {**tokens, **new_tokens}
        _save_tokens(merged)
        return merged


async def get_access_token() -> str:
    """Return a valid access token, refreshing if expired."""
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError("No Schwab tokens found — authorize via /api/v1/auth/schwab/login")

    if _is_expired(tokens):
        logger.info("Schwab access token expired, refreshing...")
        tokens = await refresh_access_token()

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# API client helpers
# ---------------------------------------------------------------------------

async def schwab_api_get(path: str, params: dict | None = None, market_data: bool = False) -> dict:
    """Make an authenticated GET request to the Schwab API."""
    access_token = await get_access_token()
    base = SCHWAB_MARKETDATA_BASE if market_data else SCHWAB_TRADER_BASE
    async with httpx.AsyncClient(base_url=base) as client:
        resp = await client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
