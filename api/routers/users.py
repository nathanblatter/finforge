"""User management endpoints — list, create, update, delete users."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import hash_password, require_auth, verify_password
from database import get_db
from models.db_models import User

logger = logging.getLogger("finforge.users")

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    id: str
    username: str
    mfa_enabled: bool
    is_active: bool
    created_at: str
    services: list[str]


class CreateUserRequest(BaseModel):
    username: str
    password: str


class UpdatePasswordRequest(BaseModel):
    current_password: str | None = None  # required for self-change, optional for admin
    new_password: str


class UpdateUserRequest(BaseModel):
    is_active: bool | None = None


class StatusResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_connected_services(db: Session) -> list[str]:
    """Determine which external services are connected based on data presence."""
    from config import settings
    import json
    from pathlib import Path

    services = []

    # Check Schwab
    token_path = Path(settings.schwab_token_file)
    if token_path.exists():
        try:
            tokens = json.loads(token_path.read_text())
            if tokens.get("access_token"):
                services.append("schwab")
        except Exception:
            pass

    # Check Plaid
    if settings.plaid_client_id and settings.plaid_client_id.strip():
        plaid_tokens = [
            getattr(settings, f, "") for f in dir(settings)
            if "plaid" in f.lower() and "access_token" in f.lower()
        ]
        if any(t for t in plaid_tokens if t):
            services.append("plaid")

    # Check Claude
    if settings.anthropic_api_key and settings.anthropic_api_key.strip():
        services.append("claude")

    return services


def _user_to_response(user: User, services: list[str]) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        username=user.username,
        mfa_enabled=user.mfa_enabled,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        services=services,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    users = db.query(User).order_by(User.created_at).all()
    services = _get_connected_services(db)
    return [_user_to_response(u, services) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("User created: %s", user.username)
    services = _get_connected_services(db)
    return _user_to_response(user, services)


@router.put("/{user_id}/password", response_model=StatusResponse)
def change_password(
    user_id: str,
    payload: UpdatePasswordRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(require_auth),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # If changing own password, verify current password
    is_self = token_payload["sub"] == str(user.id)
    if is_self and payload.current_password:
        if not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password incorrect")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    logger.info("Password changed for user: %s", user.username)
    return StatusResponse(status="ok", message="Password updated")


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UpdateUserRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_auth),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)

    services = _get_connected_services(db)
    return _user_to_response(user, services)


@router.delete("/{user_id}", response_model=StatusResponse)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(require_auth),
):
    if token_payload["sub"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    username = user.username
    db.delete(user)
    db.commit()

    logger.info("User deleted: %s", username)
    return StatusResponse(status="ok", message=f"User '{username}' deleted")


@router.get("/services", response_model=list[dict])
def get_services(
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Get detailed status of connected services."""
    from config import settings
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    services = []

    # Schwab
    schwab_status = {"name": "Schwab Trader API", "key": "schwab", "connected": False, "details": {}}
    token_path = Path(settings.schwab_token_file)
    if token_path.exists():
        try:
            tokens = json.loads(token_path.read_text())
            if tokens.get("access_token"):
                schwab_status["connected"] = True
                expires_at = tokens.get("expires_at", "")
                account_hashes = tokens.get("account_hashes", {})
                schwab_status["details"] = {
                    "accounts": list(account_hashes.keys()),
                    "token_expires": expires_at,
                    "scope": tokens.get("scope", ""),
                }
        except Exception:
            pass
    services.append(schwab_status)

    # Plaid
    plaid_status = {"name": "Plaid", "key": "plaid", "connected": False, "details": {}}
    if settings.plaid_client_id and settings.plaid_client_id.strip():
        plaid_status["connected"] = True
        plaid_status["details"] = {"environment": settings.plaid_env}
    services.append(plaid_status)

    # Claude AI
    claude_status = {"name": "Claude AI", "key": "claude", "connected": False, "details": {}}
    if settings.anthropic_api_key and settings.anthropic_api_key.strip():
        claude_status["connected"] = True
    services.append(claude_status)

    return services
