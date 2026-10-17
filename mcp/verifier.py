"""Bearer-token verification for the public MCP.

Tokens are ES256 JWTs minted by Squawk (https://squawk.nathanblatter.com)
after Nathan approves a connector in its admin console with his passkey. We
verify signature (JWKS), issuer, audience (= our service id in Squawk)
and expiry; the MCP SDK's bearer middleware then enforces required scopes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

ALGORITHMS = ["ES256"]
REQUIRED_CLAIMS = ["iss", "sub", "aud", "exp", "iat"]


class JWKSTokenVerifier:
    """Implements mcp.server.auth.provider.TokenVerifier against a JWKS issuer."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        jwks_url: str | None = None,
        leeway_seconds: int = 30,
        key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        if not issuer or not audience:
            raise ValueError("issuer and audience are required")
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.leeway = leeway_seconds
        if key_resolver is None:
            client = PyJWKClient(
                jwks_url or f"{self.issuer}/.well-known/jwks.json",
                cache_keys=True,
                lifespan=300,
            )
            key_resolver = lambda token: client.get_signing_key_from_jwt(token).key  # noqa: E731
        self._resolve_key = key_resolver

    def decode(self, token: str) -> dict[str, Any] | None:
        """Synchronous verification; None on any failure (never raises)."""
        try:
            key = self._resolve_key(token)
            return jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options={"require": REQUIRED_CLAIMS},
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        # JWKS fetches are blocking HTTP (cached 5 min); keep them off the event loop.
        claims = await anyio.to_thread.run_sync(self.decode, token)
        if claims is None:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", "")),
            scopes=str(claims.get("scope", "")).split(),
            expires_at=int(claims["exp"]),
            resource=None,  # audience was checked above; Squawk binds aud to the service id
            subject=str(claims.get("sub", "")),
            claims=claims,
        )
