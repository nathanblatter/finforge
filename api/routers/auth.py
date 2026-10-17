"""Sign-in through Squawk (Nathan's auth service) — the only way into the UI.

Flow: the login page sends the browser to Squawk's `/oauth/authorize` with PKCE
(verifier kept in the browser); Squawk parks the request and sends the browser
back to `/login?login_challenge=`; the page completes the owner-passkey, account
passkey or emailed-code ceremony through the proxy endpoints below; Squawk
redirects to `/login/callback` with a code; the page POSTs code + verifier to
`/auth/squawk/exchange`; we exchange it, verify the Squawk user token and mint
FinForge's own HS256 session JWT (what every `require_auth` site already checks).

Without `SQUAWK_ISSUER` (local dev) nothing here works and `/config` says so.
There is intentionally no password fallback: Squawk recovery codes are the
break-glass.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import squawk
from auth import create_token
from config import settings
from database import get_db
from dependencies import verify_api_key
from models.db_models import User

logger = logging.getLogger("finforge.auth")

router = APIRouter(prefix="/auth/squawk", tags=["auth"], dependencies=[Depends(verify_api_key)])


def require_squawk() -> None:
    if not squawk.enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": "Squawk sign-in is not configured"},
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mfa_required: bool = False


class SquawkConfig(BaseModel):
    enabled: bool
    issuer: str
    client_id: str
    resource: str
    redirect_uri: str
    scope: str = "admin"


class ChallengeBegin(BaseModel):
    login_challenge: str = Field(min_length=1, max_length=256)


class PasskeyFinish(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=256)
    credential: dict[str, Any]


class EmailBegin(BaseModel):
    login_challenge: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailFinish(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=256)
    code: str = Field(pattern=r"^\d{6}$")


class Exchange(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    code_verifier: str = Field(min_length=43, max_length=128)


class Redirect(BaseModel):
    redirect_to: str


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

_ERROR_MESSAGES = {
    "code_rejected": "That code is wrong or expired. Request a new one.",
    "passkey_rejected": "Passkey not recognized.",
    "setup_required": "No owner passkey is registered in Squawk yet.",
    "signup_closed": "No account exists for that address.",
    "account_disabled": "That account is disabled.",
    "email_unverified": "That account has not verified its email.",
    "too_many_attempts": "Too many attempts. Try again later.",
    "not_found": "This sign-in attempt expired. Start over.",
    "email_disabled": "Email sign-in is unavailable right now.",
    "invalid_grant": "The sign-in code was rejected. Start over.",
}


def _map_squawk_error(e: squawk.SquawkError) -> HTTPException:
    status_code = e.status if e.status in (400, 401, 403, 404, 409, 429) else 502
    headers = {"Retry-After": str(e.retry_after)} if e.status == 429 and e.retry_after else None
    message = _ERROR_MESSAGES.get(e.code) or e.detail or "Sign-in failed."
    if status_code == 502:
        logger.warning("squawk upstream error: %s", e)
        message = "Sign-in service unavailable. Try again."
    return HTTPException(status_code=status_code, detail={"error": e.code, "message": message}, headers=headers)


async def _proxy(coro):
    try:
        return await coro
    except squawk.SquawkError as e:
        raise _map_squawk_error(e)
    except Exception:
        logger.exception("squawk request error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "server_error", "message": "Sign-in service unavailable. Try again."},
        )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@router.get("/config", response_model=SquawkConfig)
def config():
    """What the login page should render and where to send the browser."""
    return SquawkConfig(
        enabled=squawk.enabled(),
        issuer=squawk.issuer(),
        client_id=settings.squawk_client_id,
        resource=settings.squawk_resource,
        redirect_uri=squawk.redirect_uri(),
    )


# ---------------------------------------------------------------------------
# Ceremony proxies (the login page at /login?login_challenge=)
# ---------------------------------------------------------------------------

_squawk_deps = [Depends(require_squawk)]


@router.post("/owner/begin", dependencies=_squawk_deps)
async def owner_begin(payload: ChallengeBegin) -> dict[str, Any]:
    """Owner sign-in: assertion options for Nathan's Squawk passkeys."""
    out = await _proxy(squawk.login_owner_begin(payload.login_challenge))
    return {"challenge_id": out["challenge_id"], "options": out["options"]}


@router.post("/owner/finish", dependencies=_squawk_deps, response_model=Redirect)
async def owner_finish(payload: PasskeyFinish):
    out = await _proxy(squawk.login_owner_finish(payload.challenge_id, payload.credential))
    return {"redirect_to": out["redirect_to"]}


@router.post("/passkey/begin", dependencies=_squawk_deps)
async def passkey_begin(payload: ChallengeBegin) -> dict[str, Any]:
    out = await _proxy(squawk.login_passkey_begin(payload.login_challenge))
    return {"challenge_id": out["challenge_id"], "options": out["options"]}


@router.post("/passkey/finish", dependencies=_squawk_deps, response_model=Redirect)
async def passkey_finish(payload: PasskeyFinish):
    out = await _proxy(squawk.login_passkey_finish(payload.challenge_id, payload.credential))
    return {"redirect_to": out["redirect_to"]}


@router.post("/email/begin", dependencies=_squawk_deps)
async def email_begin(payload: EmailBegin) -> dict[str, Any]:
    out = await _proxy(squawk.login_email_begin(payload.login_challenge, payload.email))
    return {"challenge_id": out["challenge_id"], "expires_in": out.get("expires_in", 600)}


@router.post("/email/finish", dependencies=_squawk_deps, response_model=Redirect)
async def email_finish(payload: EmailFinish):
    out = await _proxy(squawk.login_email_finish(payload.challenge_id, payload.code))
    return {"redirect_to": out["redirect_to"]}


# ---------------------------------------------------------------------------
# Code exchange → FinForge session token
# ---------------------------------------------------------------------------

@router.post("/exchange", dependencies=_squawk_deps, response_model=TokenResponse)
async def exchange(payload: Exchange, db: Session = Depends(get_db)):
    """Trade the authorization code for a Squawk user token, verify it, and
    mint FinForge's own session token for the mapped user."""
    tokens = await _proxy(squawk.exchange_code(payload.code, payload.code_verifier))
    claims = await squawk.verifier().verify(tokens.get("access_token", ""))
    if claims is None:
        logger.warning("squawk access token failed verification")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Squawk returned a token FinForge could not verify."},
        )

    sub = str(claims["sub"])
    if sub != squawk.OWNER_SUBJECT:
        # FinForge has no email column, so only the owner mapping exists today.
        logger.warning("squawk subject %s has no FinForge account", sub)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No FinForge account is linked to that Squawk account",
        )

    user = db.query(User).filter(User.username == settings.squawk_owner_username).first()
    if not user or not user.is_active:
        logger.error("owner user %r missing or inactive", settings.squawk_owner_username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No FinForge account is linked to that Squawk account",
        )

    logger.info("squawk sign-in sub=%s → user %s", sub, user.username)
    return TokenResponse(access_token=create_token(str(user.id), user.username, mfa_verified=True))
