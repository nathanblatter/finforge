"""The public instance as Claude's connector sees it: RFC 9728 metadata,
401 + WWW-Authenticate without a token, and a working MCP call with one."""

import pytest
from starlette.testclient import TestClient

from conftest import AUDIENCE, ISSUER, RESOURCE
from server import TOOLS, AuthConfig, create_server
from verifier import JWKSTokenVerifier

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def client(signing_key):
    cfg = AuthConfig(issuer=ISSUER, audience=AUDIENCE, resource=RESOURCE)
    verifier = JWKSTokenVerifier(ISSUER, AUDIENCE, key_resolver=lambda _t: signing_key.public_key())
    app = create_server(cfg, verifier).streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")
    with TestClient(app) as c:
        yield c


def test_protected_resource_metadata(client):
    r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == RESOURCE
    assert body["authorization_servers"] == [ISSUER]
    assert body["scopes_supported"] == ["read"]


def test_no_token_is_401_with_challenge(client):
    r = client.post("/mcp", json=INIT, headers=HEADERS)
    assert r.status_code == 401
    www = r.headers["WWW-Authenticate"]
    assert www.startswith("Bearer")
    assert 'resource_metadata="https://finforge.example.test/.well-known/oauth-protected-resource/mcp"' in www


def test_bad_token_is_401(client, mint, other_key):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer " + mint(key=other_key)})
    assert r.status_code == 401


def test_wrong_audience_is_401(client, mint):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer " + mint(aud="svc_other")})
    assert r.status_code == 401


def test_missing_scope_is_403(client, mint):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer " + mint(scope="")})
    assert r.status_code == 403


def test_valid_token_initializes(client, mint):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer " + mint()})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "finforge"


def test_tool_list_is_read_only(client, mint):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer " + mint()})
    assert r.status_code == 200
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={**HEADERS, "Authorization": "Bearer " + mint()},
    )
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {t.__name__ for t in TOOLS}
    for forbidden in ("dismiss", "sync", "update", "delete", "create", "set", "trigger", "run"):
        assert not any(forbidden in n for n in names), names


def test_tailnet_instance_has_no_auth():
    app = create_server(None).streamable_http_app(stateless_http=True, json_response=True, host="0.0.0.0")
    with TestClient(app) as c:
        r = c.post("/mcp", json=INIT, headers=HEADERS)
        assert r.status_code == 200
        assert c.get("/.well-known/oauth-protected-resource/mcp").status_code == 404
