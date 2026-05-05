"""User authentication endpoints — register, login, MFA setup & verify."""

import base64
import io
import logging

import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import (
    create_mfa_pending_token,
    create_token,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    require_auth,
    require_mfa_pending,
    verify_password,
    verify_totp,
)
from database import get_db
from models.db_models import User

logger = logging.getLogger("finforge.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class MFAVerifyRequest(BaseModel):
    code: str


class MFASetupConfirmRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mfa_required: bool = False


class MFASetupResponse(BaseModel):
    secret: str
    qr_code: str  # base64 PNG
    otpauth_uri: str


class StatusResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # New users get a full token — they'll set up MFA after
    token = create_token(str(user.id), user.username, mfa_verified=True)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.mfa_enabled and user.totp_secret:
        # Return a short-lived pending token — client must call /auth/mfa/verify
        pending_token = create_mfa_pending_token(str(user.id), user.username)
        return TokenResponse(access_token=pending_token, mfa_required=True)

    token = create_token(str(user.id), user.username, mfa_verified=True)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# MFA Verify (during login)
# ---------------------------------------------------------------------------

@router.post("/mfa/verify", response_model=TokenResponse)
def mfa_verify(
    payload: MFAVerifyRequest,
    token_payload: dict = Depends(require_mfa_pending),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == token_payload["sub"]).first()
    if not user or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not configured")

    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    token = create_token(str(user.id), user.username, mfa_verified=True)
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# MFA Setup — Step 1: Generate secret + QR code
# ---------------------------------------------------------------------------

@router.post("/mfa/setup", response_model=MFASetupResponse)
def mfa_setup(
    token_payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == token_payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.username)

    # Save secret (not yet enabled until confirmed)
    user.totp_secret = secret
    db.commit()

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return MFASetupResponse(secret=secret, qr_code=qr_b64, otpauth_uri=uri)


# ---------------------------------------------------------------------------
# MFA Setup — Step 2: Confirm with a code to enable
# ---------------------------------------------------------------------------

@router.post("/mfa/confirm", response_model=StatusResponse)
def mfa_confirm(
    payload: MFASetupConfirmRequest,
    token_payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == token_payload["sub"]).first()
    if not user or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run MFA setup first")

    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid code — try again")

    user.mfa_enabled = True
    db.commit()
    logger.info("MFA enabled for user %s", user.username)

    return StatusResponse(status="ok", message="MFA enabled successfully")


# ---------------------------------------------------------------------------
# MFA Disable
# ---------------------------------------------------------------------------

@router.post("/mfa/disable", response_model=StatusResponse)
def mfa_disable(
    payload: MFAVerifyRequest,
    token_payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == token_payload["sub"]).first()
    if not user or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not configured")

    if not verify_totp(user.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid code")

    user.mfa_enabled = False
    user.totp_secret = None
    db.commit()
    logger.info("MFA disabled for user %s", user.username)

    return StatusResponse(status="ok", message="MFA disabled")
