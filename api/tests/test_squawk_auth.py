"""UI sign-in through Squawk, with Squawk itself mocked at the httpx layer."""

import json
import time
import uuid
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import squawk
from auth import ALGORITHM, require_auth
from config import settings
from database import get_db
from routers.auth import router as auth_router

ISSUER = "https://squawk.example.test"
SERVICE_ID = "svc_finforge"
CLIENT_ID = "nbc_test"
RESOURCE = "https://finforge.example.test/api"
PUBLIC_URL = "https://finforge.example.test"
API_KEY_HEADERS = {"X-API-Key": "test"}  # conftest sets API_KEY=test
VERIFIER = "v" * 50


@pytest.fixture(scope="session")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def other_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def mint(signing_key):
    """Mint a user token the way Squawk does (owner by default)."""

    def _mint(key=None, **overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": "owner",
            "aud": SERVICE_ID,
            "scope": "admin",
            "client_id": CLIENT_ID,
            "iat": now,
            "exp": now + 3600,
            "jti": "x",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or signing_key, algorithm="ES256", headers={"kid": "k1", "typ": "at+jwt"})

    return _mint


@pytest.fixture
def squawk_env(monkeypatch, signing_key):
    """Configure Squawk in settings and route every outbound call to `handler`."""
    monkeypatch.setattr(settings, "squawk_issuer", ISSUER)
    monkeypatch.setattr(settings, "squawk_service_id", SERVICE_ID)
    monkeypatch.setattr(settings, "squawk_credential", "nbk_test_secret")
    monkeypatch.setattr(settings, "squawk_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "squawk_resource", RESOURCE)
    monkeypatch.setattr(settings, "public_url", PUBLIC_URL)
    monkeypatch.setattr(settings, "squawk_owner_username", "nathan")
    squawk._reset_service_token()
    monkeypatch.setattr(
        squawk, "_verifier",
        squawk.UserTokenVerifier(ISSUER, SERVICE_ID, key_resolver=lambda _tok: signing_key.public_key()),
    )
    calls = []

    class Env:
        handler = None  # set by each test: (httpx.Request) -> httpx.Response

    def dispatch(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.path == "/v1/token" and b"client_credentials" in req.content:
            form = parse_qs(req.content.decode())
            assert form["client_id"] == [SERVICE_ID] and form["client_secret"] == ["nbk_test_secret"]
            return httpx.Response(200, json={"access_token": "svc-token", "token_type": "Bearer", "expires_in": 900})
        assert Env.handler is not None, f"unexpected squawk call {req.method} {req.url}"
        return Env.handler(req)

    monkeypatch.setattr(squawk, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(dispatch)))
    Env.calls = calls
    return Env


OWNER_ID = uuid.uuid4()


@pytest.fixture
def owner_user():
    return MagicMock(id=OWNER_ID, username="nathan", is_active=True)


@pytest.fixture
def db(owner_user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = owner_user
    return db


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    c.headers.update(API_KEY_HEADERS)
    return c


# ── Config ──────────────────────────────────────────────────────────────────

def test_config_when_enabled(client, squawk_env):
    assert client.get("/auth/squawk/config").json() == {
        "enabled": True,
        "issuer": ISSUER,
        "client_id": CLIENT_ID,
        "resource": RESOURCE,
        "redirect_uri": f"{PUBLIC_URL}/login/callback",
        "scope": "admin",
    }


def test_config_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "squawk_issuer", "")
    body = client.get("/auth/squawk/config").json()
    assert body["enabled"] is False
    # Ceremonies and exchange are unreachable without Squawk.
    assert client.post("/auth/squawk/owner/begin", json={"login_challenge": "x"}).status_code == 404
    assert client.post("/auth/squawk/exchange", json={"code": "c", "code_verifier": VERIFIER}).status_code == 404


def test_requires_api_key(client, squawk_env):
    assert client.get("/auth/squawk/config", headers={"X-API-Key": "wrong"}).status_code == 401


# ── Owner / passkey ceremony proxies ────────────────────────────────────────

def test_owner_begin_and_finish(client, squawk_env):
    options = {"publicKey": {"challenge": "Y2hhbGxlbmdl", "rpId": "example.test", "userVerification": "required"}}
    seen = {}

    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer svc-token"
        if req.url.path == "/v1/login/owner/begin":
            assert json.loads(req.content) == {"login_challenge": "lc_1"}
            return httpx.Response(200, json={"challenge_id": "ch_own", "options": options})
        assert req.url.path == "/v1/login/owner/finish"
        seen["challenge"] = req.url.params["challenge"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"redirect_to": f"{PUBLIC_URL}/login/callback?code=c&state=s", "subject": "owner"})

    squawk_env.handler = handler
    r = client.post("/auth/squawk/owner/begin", json={"login_challenge": "lc_1"})
    assert r.status_code == 200 and r.json() == {"challenge_id": "ch_own", "options": options}
    cred = {"id": "abc", "rawId": "abc", "type": "public-key", "response": {"clientDataJSON": "e30"}}
    r = client.post("/auth/squawk/owner/finish", json={"challenge_id": "ch_own", "credential": cred})
    assert r.status_code == 200 and r.json() == {"redirect_to": f"{PUBLIC_URL}/login/callback?code=c&state=s"}
    assert seen == {"challenge": "ch_own", "body": cred}
    # Service token minted once and reused.
    assert [c.url.path for c in squawk_env.calls].count("/v1/token") == 1


def test_owner_begin_setup_required_maps_to_409(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(409, json={"error": "setup_required"})
    r = client.post("/auth/squawk/owner/begin", json={"login_challenge": "lc_1"})
    assert r.status_code == 409
    assert r.json()["detail"] == {"error": "setup_required", "message": "No owner passkey is registered in Squawk yet."}


def test_passkey_rejected_maps_to_401(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(401, json={"error": "passkey_rejected"})
    r = client.post("/auth/squawk/passkey/finish", json={"challenge_id": "ch", "credential": {"id": "x"}})
    assert r.status_code == 401 and r.json()["detail"]["error"] == "passkey_rejected"


def test_account_passkey_begin_proxies(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(200, json={"challenge_id": "ch_pk", "options": {"publicKey": {}}})
    r = client.post("/auth/squawk/passkey/begin", json={"login_challenge": "lc_1"})
    assert r.status_code == 200 and r.json()["challenge_id"] == "ch_pk"
    assert squawk_env.calls[-1].url.path == "/v1/login/passkey/begin"


# ── Email code proxies ──────────────────────────────────────────────────────

def test_email_begin_signup_closed_maps_to_403(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(403, json={"error": "signup_closed", "detail": "..."})
    r = client.post("/auth/squawk/email/begin", json={"login_challenge": "lc_1", "email": "stranger@example.test"})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "signup_closed"


def test_email_begin_rate_limited_maps_to_429(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(429, json={"error": "too_many_attempts"}, headers={"Retry-After": "120"})
    r = client.post("/auth/squawk/email/begin", json={"login_challenge": "lc_1", "email": "nathan@example.test"})
    assert r.status_code == 429 and r.headers["retry-after"] == "120"


def test_email_finish_returns_redirect(client, squawk_env):
    def handler(req: httpx.Request):
        assert req.url.path == "/v1/login/email/finish" and req.url.params["challenge"] == "ch_1"
        assert json.loads(req.content) == {"code": "123456"}
        return httpx.Response(200, json={"redirect_to": f"{PUBLIC_URL}/login/callback?code=c&state=s", "user": {}})

    squawk_env.handler = handler
    r = client.post("/auth/squawk/email/finish", json={"challenge_id": "ch_1", "code": "123456"})
    assert r.status_code == 200 and r.json()["redirect_to"].endswith("code=c&state=s")


def test_email_finish_validates_code_shape(client, squawk_env):
    r = client.post("/auth/squawk/email/finish", json={"challenge_id": "ch_1", "code": "12ab"})
    assert r.status_code == 422 and squawk_env.calls == []


def test_squawk_down_maps_to_502(client, squawk_env):
    def handler(req):
        raise httpx.ConnectError("refused")
    squawk_env.handler = handler
    r = client.post("/auth/squawk/owner/begin", json={"login_challenge": "lc_1"})
    assert r.status_code == 502 and r.json()["detail"]["error"] == "server_error"


def test_invalid_service_token_is_retried_once(client, squawk_env):
    state = {"n": 0}

    def handler(req: httpx.Request):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(401, json={"error": "invalid_token"}, headers={"content-type": "application/json"})
        return httpx.Response(200, json={"challenge_id": "ch", "options": {}})

    squawk_env.handler = handler
    r = client.post("/auth/squawk/owner/begin", json={"login_challenge": "lc"})
    assert r.status_code == 200
    assert [c.url.path for c in squawk_env.calls] == [
        "/v1/token", "/v1/login/owner/begin", "/v1/token", "/v1/login/owner/begin",
    ]


def test_service_token_refreshes_near_expiry(client, squawk_env, monkeypatch):
    squawk_env.handler = lambda req: httpx.Response(200, json={"challenge_id": "ch", "options": {}})
    body = {"login_challenge": "lc"}
    client.post("/auth/squawk/owner/begin", json=body)
    client.post("/auth/squawk/owner/begin", json=body)
    assert [c.url.path for c in squawk_env.calls].count("/v1/token") == 1
    monkeypatch.setattr(squawk, "_service_token_exp", time.time() + 20)  # inside the 30 s margin
    client.post("/auth/squawk/owner/begin", json=body)
    assert [c.url.path for c in squawk_env.calls].count("/v1/token") == 2


# ── Code exchange → FinForge session ────────────────────────────────────────

def _exchange_handler(token, seen):
    def handler(req: httpx.Request):
        assert req.url.path == "/oauth/token"
        assert "authorization" not in req.headers  # public client: no service token here
        seen.update({k: v[0] for k, v in parse_qs(req.content.decode()).items()})
        return httpx.Response(200, json={"access_token": token, "token_type": "Bearer", "expires_in": 3600})
    return handler


def test_exchange_maps_owner_to_finforge_user(client, squawk_env, mint, db):
    seen = {}
    squawk_env.handler = _exchange_handler(mint(), seen)
    r = client.post("/auth/squawk/exchange", json={"code": "nbac_1", "code_verifier": VERIFIER})
    assert r.status_code == 200, r.text
    assert seen == {
        "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": "nbac_1",
        "code_verifier": VERIFIER, "redirect_uri": f"{PUBLIC_URL}/login/callback",
    }
    body = r.json()
    assert body["token_type"] == "bearer" and body["mfa_required"] is False
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=[ALGORITHM])
    assert claims["sub"] == str(OWNER_ID) and claims["username"] == "nathan" and claims["mfa_verified"] is True
    # The token is a full session for every existing require_auth site.
    assert require_auth(HTTPAuthorizationCredentials(scheme="Bearer", credentials=body["access_token"]))["sub"] == str(OWNER_ID)
    # Looked up by the configured owner username.
    assert db.query.return_value.filter.called


@pytest.mark.parametrize("bad", [
    {"aud": "svc_other"},
    {"iss": "https://evil.example.test"},
    {"sub": "svc:other"},
    {"sub": "usr:abc", "email_verified": False},
    {"exp": int(time.time()) - 600},
])
def test_exchange_rejects_bad_token(client, squawk_env, mint, bad):
    squawk_env.handler = _exchange_handler(mint(**bad), {})
    r = client.post("/auth/squawk/exchange", json={"code": "nbac_1", "code_verifier": VERIFIER})
    assert r.status_code == 401 and r.json()["detail"]["error"] == "invalid_token"


def test_exchange_rejects_wrong_signing_key(client, squawk_env, mint, other_key):
    squawk_env.handler = _exchange_handler(mint(key=other_key), {})
    r = client.post("/auth/squawk/exchange", json={"code": "nbac_1", "code_verifier": VERIFIER})
    assert r.status_code == 401


def test_exchange_verified_user_without_mapping_is_403(client, squawk_env, mint):
    """A provisioned Squawk account is a valid token but FinForge has no row for it."""
    squawk_env.handler = _exchange_handler(mint(sub="usr:abc", email="x@example.test", email_verified=True), {})
    r = client.post("/auth/squawk/exchange", json={"code": "nbac_1", "code_verifier": VERIFIER})
    assert r.status_code == 403
    assert r.json()["detail"] == "No FinForge account is linked to that Squawk account"


def test_exchange_inactive_owner_is_403(client, squawk_env, mint, owner_user):
    owner_user.is_active = False
    squawk_env.handler = _exchange_handler(mint(), {})
    assert client.post("/auth/squawk/exchange", json={"code": "c", "code_verifier": VERIFIER}).status_code == 403


def test_exchange_invalid_grant_maps_to_400(client, squawk_env):
    squawk_env.handler = lambda req: httpx.Response(400, json={"error": "invalid_grant", "error_description": "used"})
    r = client.post("/auth/squawk/exchange", json={"code": "nbac_1", "code_verifier": VERIFIER})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "invalid_grant"


def test_exchange_validates_verifier_length(client, squawk_env):
    r = client.post("/auth/squawk/exchange", json={"code": "c", "code_verifier": "short"})
    assert r.status_code == 422 and squawk_env.calls == []


# ── Native login is gone ────────────────────────────────────────────────────

def test_legacy_login_routes_do_not_exist():
    """Squawk is the only sign-in: the app exposes no password, MFA or native passkey routes."""
    from main import app

    paths = {r.path for r in app.routes}
    for gone in ("/auth/login", "/auth/register", "/auth/mfa/verify", "/auth/mfa/setup", "/auth/passkeys/login/options"):
        assert f"/api/v1{gone}" not in paths
    assert "/api/v1/auth/squawk/exchange" in paths
