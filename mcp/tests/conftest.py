import os
import sys
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ISSUER = "https://auth.example.test"
AUDIENCE = "svc_finforge"
RESOURCE = "https://finforge.example.test/mcp"


@pytest.fixture(scope="session")
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def other_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def mint(signing_key):
    """Mint a token the way auth-service does (ES256, iss/sub/aud/scope/client_id/iat/exp)."""

    def _mint(key=None, **overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": "owner",
            "aud": AUDIENCE,
            "scope": "read",
            "client_id": "nbc_test",
            "iat": now,
            "exp": now + 3600,
            "jti": "x",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or signing_key, algorithm="ES256", headers={"kid": "k1", "typ": "at+jwt"})

    return _mint


@pytest.fixture
def verifier(signing_key):
    from verifier import JWKSTokenVerifier

    # Resolve keys from the test key instead of fetching a JWKS over HTTP.
    return JWKSTokenVerifier(ISSUER, AUDIENCE, key_resolver=lambda _tok: signing_key.public_key())
