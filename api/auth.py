"""JWT authentication and TOTP MFA utilities for FinForge."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user_id: str, username: str, mfa_verified: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days)
    payload = {
        "sub": user_id,
        "username": username,
        "mfa_verified": mfa_verified,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_mfa_pending_token(user_id: str, username: str) -> str:
    """Short-lived token for the MFA verification step (5 minutes)."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "sub": user_id,
        "username": username,
        "mfa_pending": True,
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
    """Validate JWT and ensure MFA is verified (if user has MFA enabled)."""
    payload = decode_token(credentials.credentials)
    if payload.get("mfa_pending"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required",
        )
    return payload


def require_mfa_pending(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Validate the short-lived MFA pending token."""
    payload = decode_token(credentials.credentials)
    if not payload.get("mfa_pending"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not an MFA pending token",
        )
    return payload


# ---------------------------------------------------------------------------
# TOTP helpers
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="FinForge"
    )


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
