"""Squawk client — Nathan's auth service (https://squawk.nathanblatter.com).

FinForge's web UI signs in through Squawk and nothing else. FinForge is
registered there as an invite-only user pool (`SQUAWK_SERVICE_ID`) whose
login page is our /login. This module holds everything that talks to Squawk:

* a cached **service token** (client_credentials with the service credential),
  which authenticates our backend when it drives the passkey / email-code
  ceremonies on behalf of the login page;
* thin helpers for `/v1/login/{owner,passkey,email}/{begin,finish}`;
* the authorization-code exchange at `/oauth/token` (PKCE; the verifier is
  generated in the browser and sent to us once with the code);
* a JWKS verifier for the **user access token** that exchange returns
  (ES256, iss == SQUAWK_ISSUER, aud == SQUAWK_SERVICE_ID, and either sub
  `owner` — Nathan with his Squawk passkey — or sub `usr:…` with
  email_verified).

All configuration comes from `config.settings`, read at call time so tests can
monkeypatch it. When `SQUAWK_ISSUER` is empty `enabled()` is False and the
sign-in endpoints answer 404; there is intentionally no local fallback.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import anyio
import httpx
import jwt
from jwt import PyJWKClient

from config import settings

log = logging.getLogger("finforge.squawk")

ALGORITHMS = ["ES256"]
REQUIRED_CLAIMS = ["iss", "sub", "aud", "exp", "iat"]
# Squawk's subject for its owner (Nathan) signing in with the owner passkey.
OWNER_SUBJECT = "owner"
HTTP_TIMEOUT = 10.0
# Refresh the service token this many seconds before it expires.
TOKEN_REFRESH_MARGIN = 30


def issuer() -> str:
    return settings.squawk_issuer.rstrip("/")


def enabled() -> bool:
    return bool(settings.squawk_issuer)


def redirect_uri() -> str:
    """The OAuth client's registered redirect_uri: the SPA's callback route."""
    return f"{settings.public_url.rstrip('/')}/login/callback"


class SquawkError(Exception):
    """A non-2xx answer from Squawk, carrying its error code so the router can
    map it to a clean response for the login page."""

    def __init__(self, status: int, code: str, detail: str = "", retry_after: int | None = None):
        super().__init__(f"squawk {status} {code}: {detail}".rstrip(": "))
        self.status = status
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


def _make_client() -> httpx.AsyncClient:
    """One client per call keeps the module free of event-loop-bound state.
    Tests monkeypatch this to inject an httpx.MockTransport."""
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT)


def _raise_for(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    code, detail = "server_error", ""
    try:
        body = resp.json()
        code = str(body.get("error") or code)
        detail = str(body.get("detail") or body.get("error_description") or "")
    except ValueError:
        detail = resp.text[:200]
    retry_after = None
    if resp.headers.get("Retry-After", "").isdigit():
        retry_after = int(resp.headers["Retry-After"])
    raise SquawkError(resp.status_code, code, detail, retry_after)


# ── Service token ───────────────────────────────────────────────────────────

_service_token: str | None = None
_service_token_exp: float = 0.0


def _reset_service_token() -> None:
    global _service_token, _service_token_exp
    _service_token, _service_token_exp = None, 0.0


async def service_token() -> str:
    """Return a valid service token, minting a new one 30 s before the old one
    expires (Squawk tokens live 15 min)."""
    global _service_token, _service_token_exp
    if _service_token and time.time() < _service_token_exp - TOKEN_REFRESH_MARGIN:
        return _service_token
    async with _make_client() as client:
        resp = await client.post(
            f"{issuer()}/v1/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.squawk_service_id,
                "client_secret": settings.squawk_credential,
            },
        )
    _raise_for(resp)
    body = resp.json()
    _service_token = body["access_token"]
    _service_token_exp = time.time() + int(body.get("expires_in", 900))
    return _service_token


async def _call(
    method: str, path: str, *, json: Any | None = None, params: dict[str, str] | None = None
) -> dict[str, Any]:
    token = await service_token()
    async with _make_client() as client:
        resp = await client.request(
            method, f"{issuer()}{path}", json=json, params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if (
        resp.status_code == 401
        and resp.headers.get("content-type", "").startswith("application/json")
        and resp.json().get("error") == "invalid_token"
    ):
        # Service token revoked/rotated under us: mint a fresh one and retry once.
        _reset_service_token()
        token = await service_token()
        async with _make_client() as client:
            resp = await client.request(
                method, f"{issuer()}{path}", json=json, params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    _raise_for(resp)
    return resp.json()


# ── Login ceremonies (driven for the login page) ────────────────────────────

async def login_owner_begin(login_challenge: str) -> dict[str, Any]:
    """→ {"challenge_id", "options"}; assertion options for the *owner's* Squawk
    passkeys (RP ID = nathanblatter.com, accepted from FinForge's origin)."""
    return await _call("POST", "/v1/login/owner/begin", json={"login_challenge": login_challenge})


async def login_owner_finish(challenge_id: str, credential: dict[str, Any]) -> dict[str, Any]:
    """→ {"redirect_to", "subject": "owner"}."""
    return await _call("POST", "/v1/login/owner/finish", json=credential, params={"challenge": challenge_id})


async def login_passkey_begin(login_challenge: str) -> dict[str, Any]:
    """→ {"challenge_id", "options"}; options are WebAuthn assertion options."""
    return await _call("POST", "/v1/login/passkey/begin", json={"login_challenge": login_challenge})


async def login_passkey_finish(challenge_id: str, credential: dict[str, Any]) -> dict[str, Any]:
    """→ {"redirect_to", "user"}; credential is the browser's assertion JSON."""
    return await _call("POST", "/v1/login/passkey/finish", json=credential, params={"challenge": challenge_id})


async def login_email_begin(login_challenge: str, email: str) -> dict[str, Any]:
    """→ {"challenge_id", "expires_in"}; Squawk mails a 6-digit code."""
    return await _call("POST", "/v1/login/email/begin", json={"login_challenge": login_challenge, "email": email})


async def login_email_finish(challenge_id: str, code: str) -> dict[str, Any]:
    """→ {"redirect_to", "user"}; send the browser to redirect_to."""
    return await _call("POST", "/v1/login/email/finish", json={"code": code}, params={"challenge": challenge_id})


# ── Authorization-code exchange ─────────────────────────────────────────────

async def exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    """PKCE code exchange for our first-party (public) OAuth client."""
    async with _make_client() as client:
        resp = await client.post(
            f"{issuer()}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.squawk_client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri(),
            },
        )
    _raise_for(resp)
    return resp.json()


# ── User access-token verification ──────────────────────────────────────────

class UserTokenVerifier:
    """Verifies a Squawk user access token against the issuer's JWKS."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        key_resolver: Callable[[str], Any] | None = None,
        leeway_seconds: int = 30,
    ) -> None:
        if not issuer or not audience:
            raise ValueError("issuer and audience are required")
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.leeway = leeway_seconds
        if key_resolver is None:
            jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=300)
            key_resolver = lambda token: jwks.get_signing_key_from_jwt(token).key  # noqa: E731
        self._resolve_key = key_resolver

    def decode(self, token: str) -> dict[str, Any] | None:
        """Claims when the token is a valid, verified *user* token for this
        service; None otherwise. Never raises."""
        try:
            key = self._resolve_key(token)
            claims = jwt.decode(
                token, key,
                algorithms=ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options={"require": REQUIRED_CLAIMS},
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None
        sub = str(claims.get("sub", ""))
        if sub == OWNER_SUBJECT:
            return claims
        if not sub.startswith("usr:") or claims.get("email_verified") is not True:
            return None
        return claims

    async def verify(self, token: str) -> dict[str, Any] | None:
        # The JWKS fetch is blocking HTTP (cached 5 min); keep it off the loop.
        return await anyio.to_thread.run_sync(self.decode, token)


_verifier: UserTokenVerifier | None = None


def verifier() -> UserTokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = UserTokenVerifier(issuer(), settings.squawk_service_id)
    return _verifier
