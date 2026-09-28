"""JWT authentication, TOTP MFA, and passkey (WebAuthn) token utilities for FinForge."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str | None) -> bool:
    """False when the account has no password (passkey-only)."""
    if not hashed:
        return False
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


# ---------------------------------------------------------------------------
# Passkey tokens
# ---------------------------------------------------------------------------

PASSKEY_ENROLL_PURPOSE = "passkey_enroll"
PASSKEY_CHALLENGE_PURPOSE = "passkey_challenge"


def create_passkey_enroll_token(user_id: str, username: str, ttl_minutes: int = 15) -> str:
    """One-time-style magic link token: lets a user register their FIRST passkey
    without a password or existing session. Short-lived; grants nothing else."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "purpose": PASSKEY_ENROLL_PURPOSE,
        "jti": uuid.uuid4().hex,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_passkey_challenge_token(challenge: bytes, kind: str, user_id: str | None = None) -> str:
    """Stateless carrier for a WebAuthn challenge so verification works across
    API replicas (no server-side session store). 5-minute lifetime."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "purpose": PASSKEY_CHALLENGE_PURPOSE,
        "kind": kind,  # "register" | "login"
        "challenge": bytes_to_base64url(challenge),
        "exp": exp,
    }
    if user_id is not None:
        payload["sub"] = user_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_passkey_challenge_token(token: str, kind: str) -> tuple[bytes, str | None]:
    payload = decode_token(token)
    if payload.get("purpose") != PASSKEY_CHALLENGE_PURPOSE or payload.get("kind") != kind:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid challenge token")
    return base64url_to_bytes(payload["challenge"]), payload.get("sub")


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
    if payload.get("purpose"):
        # Enrollment / challenge tokens are never a session.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


def require_auth_or_passkey_enroll(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Accept either a full session token or a passkey enrollment token.
    Used only by passkey registration so a magic link can bootstrap the first passkey."""
    payload = decode_token(credentials.credentials)
    if payload.get("purpose") == PASSKEY_ENROLL_PURPOSE:
        return payload
    if payload.get("mfa_pending") or payload.get("purpose"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
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
