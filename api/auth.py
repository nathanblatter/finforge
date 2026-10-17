"""FinForge session tokens (HS256 JWT).

Sign-in happens through Squawk (see routers/auth.py); once a Squawk user token
is verified we mint one of these, and every protected endpoint checks it with
`require_auth`. `mfa_verified` is kept in the payload for compatibility with
tokens issued before Squawk — it is always True now.
"""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings

bearer = HTTPBearer()

ALGORITHM = "HS256"


def create_token(user_id: str, username: str, mfa_verified: bool = True) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {
        "sub": user_id,
        "username": username,
        "mfa_verified": mfa_verified,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


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
