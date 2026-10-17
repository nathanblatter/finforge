"""FinForge session tokens (HS256 JWT).

Sign-in happens through Squawk (see routers/auth.py); once a Squawk user token
is verified we mint one of these, and every protected endpoint checks it with
`require_auth`. FinForge has no users table: `sub` IS the identity — the Squawk
subject string ("owner" for Nathan's passkey, "usr:<id>" for a provisioned
account) — and per-user rows are keyed on it directly.
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings

bearer = HTTPBearer()

ALGORITHM = "HS256"


def create_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def subject_of(payload: dict) -> str:
    """The Squawk subject a validated session token belongs to."""
    return str(payload["sub"])


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Validate the session JWT. Pending/limited-purpose tokens from the
    retired native login (mfa_pending, passkey enrollment/challenge) are never
    a session."""
    payload = decode_token(credentials.credentials)
    if payload.get("mfa_pending"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required",
        )
    if payload.get("purpose"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload
