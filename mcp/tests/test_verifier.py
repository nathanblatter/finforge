import pytest

from conftest import AUDIENCE, ISSUER


def test_valid_token_yields_access_token(verifier, mint):
    import anyio

    tok = anyio.run(verifier.verify_token, mint(scope="read"))
    assert tok is not None
    assert tok.client_id == "nbc_test"
    assert tok.scopes == ["read"]
    assert tok.subject == "owner"
    assert tok.claims["aud"] == AUDIENCE


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "svc_other"},  # token for another service
        {"iss": ISSUER + "x"},  # wrong issuer
        {"exp": 1},  # expired
        {"sub": None},  # missing required claim
    ],
)
def test_rejects_bad_claims(verifier, mint, overrides):
    assert verifier.decode(mint(**overrides)) is None


def test_rejects_wrong_signature(verifier, mint, other_key):
    assert verifier.decode(mint(key=other_key)) is None


def test_rejects_garbage(verifier):
    assert verifier.decode("not.a.jwt") is None
    assert verifier.decode("") is None


def test_issuer_trailing_slash_normalised(signing_key):
    from verifier import JWKSTokenVerifier

    v = JWKSTokenVerifier(ISSUER + "/", AUDIENCE, key_resolver=lambda _t: signing_key.public_key())
    assert v.issuer == ISSUER


def test_requires_issuer_and_audience():
    from verifier import JWKSTokenVerifier

    with pytest.raises(ValueError):
        JWKSTokenVerifier("", AUDIENCE)
    with pytest.raises(ValueError):
        JWKSTokenVerifier(ISSUER, "")
