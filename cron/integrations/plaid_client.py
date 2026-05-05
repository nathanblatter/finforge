"""Plaid API client factory for FinForge."""

import plaid
from plaid.api import plaid_api

from config import settings

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Production,
    "production": plaid.Environment.Production,
}


def get_plaid_client() -> plaid_api.PlaidApi:
    """
    Create and return a configured Plaid API client.
    Uses PLAID_ENV setting to select the correct host.
    """
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
