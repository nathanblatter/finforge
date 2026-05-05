"""
Schwab OAuth token management for FinForge.

Tokens are stored in a JSON file on disk ONLY — never in the database.

Token file schema:
{
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": "2026-03-27T03:00:00+00:00",   # ISO 8601 UTC
    "account_hashes": {
        "Schwab Brokerage": "obfuscated-hash-string",
        "Schwab Roth IRA":  "obfuscated-hash-string"
    }
}

PRD requirements:
  - Access token refreshed when within 5 minutes of expiry
  - Refresh token rolled forward every nightly run (7-day window)
  - Re-auth alert on 401 / invalid_client (refresh token expired)
  - Atomic file writes to prevent corruption
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
ACCESS_TOKEN_BUFFER_SECONDS = 300  # refresh if expiring within 5 minutes


class SchwabReauthRequired(Exception):
    """
    Raised when the Schwab refresh token has expired.
    Manual browser-based re-authentication is required.
    """


class SchwabTokenManager:
    """
    Manages Schwab OAuth tokens stored in a JSON file on disk.

    Handles:
      - Loading and saving tokens with atomic writes
      - Access token refresh before expiry
      - Detection of expired refresh tokens (triggers SchwabReauthRequired)
      - Persistence of account hash mappings alongside tokens
    """

    def __init__(self, token_file_path: str, client_id: str, client_secret: str) -> None:
        self.token_file_path = token_file_path
        self.client_id = client_id
        self.client_secret = client_secret
        self._tokens: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Token file I/O
    # ------------------------------------------------------------------

    def load_tokens(self) -> dict[str, Any]:
        """
        Load tokens from the JSON file on disk.

        Raises:
            FileNotFoundError: If the token file does not exist (initial setup needed).
            ValueError: If the file is malformed.
        """
        with open(self.token_file_path, "r") as f:
            data = json.load(f)
        required = {"access_token", "refresh_token", "expires_at"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Token file missing required keys: {missing}")
        self._tokens = data
        return data

    def save_tokens(self, tokens: dict[str, Any]) -> None:
        """
        Atomically write tokens to the JSON file.
        Uses write-to-temp + os.replace() to prevent file corruption.
        Never logs or exposes token values.
        """
        tmp_path = self.token_file_path + ".tmp"
        os.makedirs(os.path.dirname(self.token_file_path), exist_ok=True)
        with open(tmp_path, "w") as f:
            json.dump(tokens, f, indent=2)
        os.replace(tmp_path, self.token_file_path)
        self._tokens = tokens
        logger.debug("Schwab token file updated (expires_at=%s)", tokens.get("expires_at"))

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def get_valid_access_token(self) -> str:
        """
        Return a valid access token, refreshing if it is within
        ACCESS_TOKEN_BUFFER_SECONDS of expiry.

        Raises:
            SchwabReauthRequired: If the refresh token is expired or rejected.
            FileNotFoundError: If the token file has not been initialized.
        """
        tokens = self._tokens or self.load_tokens()
        expires_at = datetime.fromisoformat(tokens["expires_at"])

        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now >= expires_at - timedelta(seconds=ACCESS_TOKEN_BUFFER_SECONDS):
            logger.info("Schwab access token near expiry — refreshing")
            tokens = self.refresh_access_token(tokens["refresh_token"])
            self.save_tokens({**self._tokens, **tokens})

        return self._tokens["access_token"]

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """
        Exchange a refresh token for a new access token via Schwab token endpoint.

        Args:
            refresh_token: The current refresh token (not logged).

        Returns:
            Dict with access_token, refresh_token, expires_at keys.

        Raises:
            SchwabReauthRequired: On 401 or invalid_client response.
            httpx.HTTPError: On unexpected HTTP errors.
        """
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        try:
            response = httpx.post(
                SCHWAB_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=30,
            )
        except httpx.HTTPError as exc:
            logger.error("HTTP error during Schwab token refresh: %s", exc)
            raise

        if response.status_code == 401:
            logger.critical(
                "Schwab re-authentication required — refresh token expired. "
                "Manual browser auth needed. Run the Schwab OAuth setup flow."
            )
            raise SchwabReauthRequired("Schwab refresh token expired — manual re-auth needed")

        if not response.is_success:
            body = response.text
            if "invalid_client" in body:
                logger.critical(
                    "Schwab invalid_client error — refresh token rejected. "
                    "Manual browser auth needed."
                )
                raise SchwabReauthRequired("Schwab invalid_client — manual re-auth needed")
            logger.error("Schwab token refresh failed (%d): %s", response.status_code, body[:200])
            response.raise_for_status()

        data = response.json()
        expires_in = int(data.get("expires_in", 1800))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),  # roll forward if provided
            "expires_at": expires_at,
        }

    def force_refresh(self) -> None:
        """
        Unconditionally refresh the access token (and roll the refresh token).
        Called every nightly run to reset the 7-day refresh token window.
        """
        tokens = self._tokens or self.load_tokens()
        logger.info("Schwab: forcing token refresh to roll 7-day refresh token window")
        new_tokens = self.refresh_access_token(tokens["refresh_token"])
        self.save_tokens({**tokens, **new_tokens})

    # ------------------------------------------------------------------
    # Account hash management
    # ------------------------------------------------------------------

    def get_account_hashes(self) -> dict[str, str]:
        """
        Return the alias → accountHash mapping stored in the token file.
        Returns an empty dict if not yet populated (first run).
        """
        tokens = self._tokens or self.load_tokens()
        return tokens.get("account_hashes", {})

    def update_account_hashes(self, hashes: dict[str, str]) -> None:
        """
        Merge updated alias → accountHash mappings into the token file.
        accountHash is Schwab's obfuscated identifier — not a real account number.
        """
        tokens = self._tokens or self.load_tokens()
        existing = tokens.get("account_hashes", {})
        existing.update(hashes)
        self.save_tokens({**tokens, "account_hashes": existing})
        logger.debug("Schwab account hashes updated for aliases: %s", list(hashes.keys()))
