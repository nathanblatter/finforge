"""Passkey (WebAuthn) endpoints — register, authenticate, list, revoke.

Challenges are carried in short-lived signed tokens rather than server memory
so the flow is safe across the two API replicas used by zero-downtime deploys.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from auth import (
    create_passkey_challenge_token,
    create_token,
    decode_passkey_challenge_token,
    require_auth,
    require_auth_or_passkey_enroll,
)
from config import settings
from database import get_db
from models.db_models import Passkey, User

logger = logging.getLogger("finforge.passkeys")

router = APIRouter(prefix="/auth/passkeys", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OptionsResponse(BaseModel):
    options: dict
    challenge_token: str


class RegisterVerifyRequest(BaseModel):
    credential: dict
    challenge_token: str
    name: str = "Passkey"


class LoginOptionsRequest(BaseModel):
    username: str | None = None


class LoginVerifyRequest(BaseModel):
    credential: dict
    challenge_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mfa_required: bool = False


class PasskeyInfo(BaseModel):
    id: str
    name: str
    created_at: str
    last_used_at: str | None
    backed_up: bool


class StatusResponse(BaseModel):
    status: str
    message: str


def _load_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register/options", response_model=OptionsResponse)
def register_options(
    token_payload: dict = Depends(require_auth_or_passkey_enroll),
    db: Session = Depends(get_db),
):
    user = _load_user(db, token_payload["sub"])
    existing = db.query(Passkey).filter(Passkey.user_id == user.id).all()

    options = generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=user.id.bytes,
        user_name=user.username,
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=p.credential_id) for p in existing
        ],
    )
    return OptionsResponse(
        options=json.loads(options_to_json(options)),
        challenge_token=create_passkey_challenge_token(
            options.challenge, kind="register", user_id=str(user.id)
        ),
    )


@router.post("/register/verify", response_model=TokenResponse)
def register_verify(
    payload: RegisterVerifyRequest,
    token_payload: dict = Depends(require_auth_or_passkey_enroll),
    db: Session = Depends(get_db),
):
    challenge, challenge_user = decode_passkey_challenge_token(payload.challenge_token, "register")
    if challenge_user != token_payload["sub"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge/user mismatch")
    user = _load_user(db, token_payload["sub"])

    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        logger.warning("Passkey registration failed for %s: %s", user.username, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Registration failed: {exc}")

    if db.query(Passkey).filter(Passkey.credential_id == verified.credential_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Passkey already registered")

    transports = payload.credential.get("response", {}).get("transports") or None
    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=transports,
        name=(payload.name or "Passkey")[:100],
        aaguid=verified.aaguid,
        backed_up=verified.credential_backed_up,
    )
    db.add(passkey)
    db.commit()
    logger.info("Passkey %r registered for user %s", passkey.name, user.username)

    # Registering with a magic-link enrollment token also signs the user in.
    return TokenResponse(access_token=create_token(str(user.id), user.username, mfa_verified=True))


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@router.post("/login/options", response_model=OptionsResponse)
def login_options(payload: LoginOptionsRequest, db: Session = Depends(get_db)):
    allow: list[PublicKeyCredentialDescriptor] | None = None
    if payload.username:
        # Don't reveal whether the username exists — an empty allow list still
        # produces a valid (discoverable-credential) request.
        user = db.query(User).filter(User.username == payload.username).first()
        if user:
            allow = [
                PublicKeyCredentialDescriptor(id=p.credential_id)
                for p in db.query(Passkey).filter(Passkey.user_id == user.id).all()
            ] or None

    options = generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return OptionsResponse(
        options=json.loads(options_to_json(options)),
        challenge_token=create_passkey_challenge_token(options.challenge, kind="login"),
    )


@router.post("/login/verify", response_model=TokenResponse)
def login_verify(payload: LoginVerifyRequest, db: Session = Depends(get_db)):
    challenge, _ = decode_passkey_challenge_token(payload.challenge_token, "login")

    raw_id = payload.credential.get("rawId") or payload.credential.get("id")
    if not raw_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing credential id")
    passkey = (
        db.query(Passkey).filter(Passkey.credential_id == base64url_to_bytes(raw_id)).first()
    )
    if not passkey:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown passkey")
    user = passkey.user
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        logger.warning("Passkey login failed for %s: %s", user.username, exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey verification failed")

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Passkey login for user %s (%s)", user.username, passkey.name)

    # A passkey with user verification is already possession + biometric/PIN:
    # it satisfies MFA, so no TOTP step.
    return TokenResponse(access_token=create_token(str(user.id), user.username, mfa_verified=True))


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PasskeyInfo])
def list_passkeys(token_payload: dict = Depends(require_auth), db: Session = Depends(get_db)):
    rows = (
        db.query(Passkey)
        .filter(Passkey.user_id == token_payload["sub"])
        .order_by(Passkey.created_at)
        .all()
    )
    return [
        PasskeyInfo(
            id=str(p.id),
            name=p.name,
            created_at=p.created_at.isoformat() if p.created_at else "",
            last_used_at=p.last_used_at.isoformat() if p.last_used_at else None,
            backed_up=p.backed_up,
        )
        for p in rows
    ]


@router.delete("/{passkey_id}", response_model=StatusResponse)
def delete_passkey(
    passkey_id: str,
    token_payload: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    passkey = (
        db.query(Passkey)
        .filter(Passkey.id == passkey_id, Passkey.user_id == token_payload["sub"])
        .first()
    )
    if not passkey:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")

    user = passkey.user
    remaining = db.query(Passkey).filter(Passkey.user_id == user.id).count() - 1
    if remaining == 0 and not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This is your only sign-in method; add another passkey first",
        )

    db.delete(passkey)
    db.commit()
    logger.info("Passkey %r removed for user %s", passkey.name, user.username)
    return StatusResponse(status="ok", message="Passkey removed")
