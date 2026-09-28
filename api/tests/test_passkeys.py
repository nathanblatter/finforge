"""Passkey token plumbing + passkey-only login guard.

Full WebAuthn ceremonies need a real authenticator, so these cover the parts
we own: challenge/enrollment tokens, dependency gating, and the password path.
"""

import os
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import (
    create_passkey_challenge_token,
    create_passkey_enroll_token,
    create_token,
    decode_passkey_challenge_token,
    require_auth,
    require_auth_or_passkey_enroll,
    verify_password,
)
from database import get_db
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from routers.auth import router as auth_router
from routers.passkeys import router as passkeys_router


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_challenge_token_roundtrip():
    challenge = os.urandom(32)
    tok = create_passkey_challenge_token(challenge, kind="register", user_id="u1")
    got, sub = decode_passkey_challenge_token(tok, "register")
    assert got == challenge and sub == "u1"


def test_challenge_token_kind_mismatch_rejected():
    tok = create_passkey_challenge_token(os.urandom(32), kind="login")
    with pytest.raises(HTTPException) as exc:
        decode_passkey_challenge_token(tok, "register")
    assert exc.value.status_code == 400


def test_enroll_token_is_not_a_session():
    tok = create_passkey_enroll_token("u1", "nathan")
    with pytest.raises(HTTPException) as exc:
        require_auth(_creds(tok))
    assert exc.value.status_code == 401
    # ...but it is accepted by the registration-only dependency.
    assert require_auth_or_passkey_enroll(_creds(tok))["sub"] == "u1"


def test_challenge_token_cannot_register():
    tok = create_passkey_challenge_token(os.urandom(32), kind="register", user_id="u1")
    with pytest.raises(HTTPException):
        require_auth_or_passkey_enroll(_creds(tok))


def test_session_token_still_valid_everywhere():
    tok = create_token("u1", "nathan", mfa_verified=True)
    assert require_auth(_creds(tok))["sub"] == "u1"
    assert require_auth_or_passkey_enroll(_creds(tok))["sub"] == "u1"


def test_verify_password_false_for_passkey_only_account():
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False


def _app_with_user(user):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(passkeys_router)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_password_login_rejected_for_passkey_only_user():
    user = MagicMock(id=uuid.uuid4(), username="nathan", password_hash=None, is_active=True)
    client = _app_with_user(user)
    res = client.post("/auth/login", json={"username": "nathan", "password": "x"})
    assert res.status_code == 401


def test_register_options_requires_enroll_or_session_token():
    client = _app_with_user(None)
    assert client.post("/auth/passkeys/register/options").status_code in (401, 403)
    chal = create_passkey_challenge_token(os.urandom(32), kind="register", user_id="u1")
    res = client.post(
        "/auth/passkeys/register/options", headers={"Authorization": f"Bearer {chal}"}
    )
    assert res.status_code == 401


def test_register_verify_rejects_challenge_for_other_user():
    uid = uuid.uuid4()
    user = MagicMock(id=uid, username="nathan", password_hash=None, is_active=True)
    client = _app_with_user(user)
    enroll = create_passkey_enroll_token(str(uid), "nathan")
    chal = create_passkey_challenge_token(os.urandom(32), kind="register", user_id="someone-else")
    res = client.post(
        "/auth/passkeys/register/verify",
        headers={"Authorization": f"Bearer {enroll}"},
        json={"credential": {}, "challenge_token": chal, "name": "Mac"},
    )
    assert res.status_code == 400
