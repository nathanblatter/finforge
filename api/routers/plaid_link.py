"""Plaid Link endpoints — create link tokens and exchange public tokens."""

import json
import logging
import os
from pathlib import Path

import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth import require_auth
from config import settings

logger = logging.getLogger("finforge.plaid_link")

router = APIRouter(prefix="/plaid", tags=["plaid"])

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Sandbox,  # Plaid SDK only has Sandbox + Production
    "production": plaid.Environment.Production,
}

PLAID_TOKENS_FILE = "/secrets/plaid_tokens.json"


def _get_plaid_client() -> plaid_api.PlaidApi:
    host = _ENV_MAP.get(settings.plaid_env.lower(), plaid.Environment.Sandbox)
    configuration = plaid.Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def _load_plaid_tokens() -> dict:
    path = Path(PLAID_TOKENS_FILE)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_plaid_tokens(tokens: dict) -> None:
    path = Path(PLAID_TOKENS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tokens, f, indent=2)
    os.replace(tmp, str(path))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str
    accounts: list[dict]  # [{id, name, type, subtype}]


class ExchangeResponse(BaseModel):
    status: str
    institution: str
    accounts_linked: list[str]


class PlaidStatusResponse(BaseModel):
    institution: str
    accounts: list[str]
    linked: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/link-token", response_model=LinkTokenResponse)
def create_link_token(
    token_payload: dict = Depends(require_auth),
):
    """Create a Plaid Link token for the frontend to initiate Link."""
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plaid not configured")

    client = _get_plaid_client()
    user_id = token_payload["sub"]

    # WF and Amex use OAuth — redirect_uri is required for OAuth institutions
    redirect_uri = "https://finforge.nathanblatter.com/api/v1/plaid/oauth-callback"

    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        client_name="FinForge",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
        redirect_uri=redirect_uri,
    )

    try:
        response = client.link_token_create(request)
        return LinkTokenResponse(link_token=response.link_token)
    except plaid.ApiException as exc:
        logger.error("Plaid link_token_create failed: %s", exc.body if hasattr(exc, "body") else exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to create link token")


@router.post("/exchange", response_model=ExchangeResponse)
def exchange_public_token(
    payload: ExchangeRequest,
    _: dict = Depends(require_auth),
):
    """Exchange a public_token from Plaid Link for a permanent access_token."""
    client = _get_plaid_client()

    request = ItemPublicTokenExchangeRequest(public_token=payload.public_token)
    try:
        response = client.item_public_token_exchange(request)
    except plaid.ApiException as exc:
        logger.error("Plaid public_token exchange failed: %s", exc.body if hasattr(exc, "body") else exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Token exchange failed")

    access_token = response.access_token
    item_id = response.item_id

    # Save access token keyed by institution
    tokens = _load_plaid_tokens()
    inst = payload.institution_name.lower().replace(" ", "_")

    account_names = []
    for acct in payload.accounts:
        acct_name = acct.get("name", "Unknown")
        acct_subtype = acct.get("subtype", "")
        account_names.append(f"{acct_name} ({acct_subtype})")

    tokens[inst] = {
        "access_token": access_token,
        "item_id": item_id,
        "institution": payload.institution_name,
        "accounts": payload.accounts,
    }
    _save_plaid_tokens(tokens)

    logger.info("Plaid token saved for %s — %d accounts", payload.institution_name, len(payload.accounts))

    return ExchangeResponse(
        status="ok",
        institution=payload.institution_name,
        accounts_linked=account_names,
    )


@router.get("/oauth-callback")
def plaid_oauth_callback():
    """
    OAuth redirect landing. After bank login, Plaid redirects here.
    The frontend re-opens Plaid Link with the same link_token to complete the flow.
    Redirect to the frontend settings page with oauth_state_id param.
    """
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/settings?oauth=true")


@router.get("/status", response_model=list[PlaidStatusResponse])
def get_plaid_status(_: dict = Depends(require_auth)):
    """Get status of linked Plaid institutions."""
    tokens = _load_plaid_tokens()
    result = []

    for key, data in tokens.items():
        accounts = [
            f"{a.get('name', '?')} ({a.get('subtype', '?')})"
            for a in data.get("accounts", [])
        ]
        result.append(PlaidStatusResponse(
            institution=data.get("institution", key),
            accounts=accounts,
            linked=True,
        ))

    return result
