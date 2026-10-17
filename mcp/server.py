"""FinForge MCP server — read-only financial tools for agents.

Thin wrapper over the FinForge REST API (mirrors the flightdeck pattern:
streamable-HTTP MCP). Two deployments of this one program:

* tailnet instance (no AUTH_* env): unauthenticated, bound to the tailnet;
  consumers are natebot's brain sessions and Claude Code on the tailnet.
* public instance (AUTH_ISSUER set): reachable at
  https://finforge.nathanblatter.com/mcp behind nginx + the Cloudflare tunnel;
  every request must carry a bearer token minted by Squawk, which
  Nathan approves per connector with his passkey. Used by Claude on his phone.

Read-only by design: write routes (dismiss anomaly, mark-legit, rules, syncs)
are not exposed on either instance.
"""

import os
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from verifier import JWKSTokenVerifier

API_URL = os.getenv("FINFORGE_API_URL", "http://finforge-api:8000/api/v1")
API_KEY = os.getenv("FINFORGE_API_KEY", "")


@dataclass(frozen=True)
class AuthConfig:
    """Public-instance settings; all three come from the environment."""

    issuer: str  # https://squawk.nathanblatter.com
    audience: str  # our service id in Squawk (svc_…), the token's aud
    resource: str  # https://finforge.nathanblatter.com/mcp (RFC 8707 resource)
    required_scopes: tuple[str, ...] = ("read",)

    @classmethod
    def from_env(cls) -> "AuthConfig | None":
        issuer = os.getenv("AUTH_ISSUER", "").strip()
        if not issuer:
            return None
        audience = os.getenv("AUTH_AUDIENCE", "").strip()
        resource = os.getenv("AUTH_RESOURCE", "").strip()
        if not audience or not resource:
            raise SystemExit("AUTH_ISSUER is set; AUTH_AUDIENCE and AUTH_RESOURCE are required too")
        scopes = tuple(os.getenv("AUTH_REQUIRED_SCOPES", "read").split()) or ("read",)
        return cls(issuer=issuer, audience=audience, resource=resource, required_scopes=scopes)


def create_server(auth: AuthConfig | None = None, verifier: JWKSTokenVerifier | None = None) -> MCPServer:
    """Build the server; with `auth` every MCP request needs a valid Squawk token."""
    if auth is None:
        server = MCPServer("finforge")
    else:
        server = MCPServer(
            "finforge",
            token_verifier=verifier or JWKSTokenVerifier(auth.issuer, auth.audience),
            auth=AuthSettings(
                issuer_url=auth.issuer,
                resource_server_url=auth.resource,
                required_scopes=list(auth.required_scopes),
                # The verifier checks `aud` itself (Squawk binds tokens to the
                # service id, not the resource URL), so the SDK must not compare resources.
                validate_token_resource=False,
            ),
        )
    for tool in TOOLS:
        server.tool()(tool)
    return server


_client = httpx.AsyncClient(
    base_url=API_URL,
    headers={"X-API-Key": API_KEY},
    timeout=30.0,
)


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    resp = await _client.get(path, params=params)
    if resp.status_code >= 400:
        # Surface the API's own message (e.g. a 422 validation detail) so the model can
        # correct its arguments instead of seeing an opaque "error executing tool".
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ToolError(f"FinForge API {resp.status_code} for {path}: {detail}")
    ctype = resp.headers.get("content-type", "")
    return resp.json() if ctype.startswith("application/json") else resp.text


async def get_summary() -> Any:
    """Full financial state snapshot: balances, net worth, accounts."""
    return await _get("/summary")


async def get_briefing() -> Any:
    """Pre-formatted daily financial briefing (net worth, portfolio risk, alerts) as readable text."""
    return await _get("/natebot/imessage/briefing")


async def get_portfolio() -> Any:
    """Current investment portfolio: positions, allocation, risk — as readable text."""
    return await _get("/natebot/imessage/portfolio")


async def get_financial_goals() -> Any:
    """Financial goals and progress toward them, as readable text."""
    return await _get("/natebot/imessage/goals")


async def get_watchlist() -> Any:
    """Stock watchlist with current prices, as readable text."""
    return await _get("/natebot/imessage/watchlist")


async def spending_monthly(month: str | None = None) -> Any:
    """Monthly spending breakdown by category. month: 'YYYY-MM', defaults to current month."""
    return await _get("/spending/monthly", {"month": month})


async def list_transactions(
    days: int | None = None,
    month: str | None = None,
    category: str | None = None,
    account_alias: str | None = None,
    include_pending: bool | None = None,
    limit: int | None = None,
) -> Any:
    """List transactions, filterable by recency (days), month ('YYYY-MM'), category, or account."""
    return await _get(
        "/spending/transactions",
        {
            "days": days,
            "month": month,
            "category": category,
            "account_alias": account_alias,
            "include_pending": include_pending,
            "limit": limit,
        },
    )


async def search_transactions(q: str) -> Any:
    """Full-text search over transactions (merchant names, descriptions)."""
    return await _get("/spending/search", {"q": q})


async def merchant_spending(name: str) -> Any:
    """Spending history and stats for a single merchant."""
    return await _get("/spending/merchant", {"name": name})


async def get_subscriptions(months: int | None = None) -> Any:
    """Detected recurring subscriptions over the lookback window (months)."""
    return await _get("/spending/subscriptions", {"months": months})


async def spending_forecast(months: int | None = None) -> Any:
    """Next-month spend forecast per category (80% confidence band) plus this month's
    run-rate projection. `months` is the HISTORY window used to fit the forecast
    (4-24 complete months, default 12), not the forecast horizon."""
    return await _get("/spending/forecast", {"months": months})


async def get_anomalies(include_dismissed: bool | None = None, limit: int | None = None) -> Any:
    """Unusual-spending anomalies flagged by FinForge."""
    return await _get("/spending/anomalies", {"include_dismissed": include_dismissed, "limit": limit})


async def charge_guardian(status: str | None = None, kind: str | None = None, limit: int | None = None) -> Any:
    """Charge-guardian findings: suspicious/duplicate/price-hike charges needing review."""
    return await _get("/spending/charge-guardian", {"status": status, "kind": kind, "limit": limit})


# Every tool is a GET against the API: the read-only guarantee lives here.
TOOLS = [
    get_summary,
    get_briefing,
    get_portfolio,
    get_financial_goals,
    get_watchlist,
    spending_monthly,
    list_transactions,
    search_transactions,
    merchant_spending,
    get_subscriptions,
    spending_forecast,
    get_anomalies,
    charge_guardian,
]


if __name__ == "__main__":
    auth = AuthConfig.from_env()
    create_server(auth).run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        stateless_http=True,
        json_response=True,
        # Behind nginx + the Cloudflare tunnel the Host header is the public
        # hostname; the SDK's DNS-rebinding guard is for servers exposed directly.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False) if auth else None,
    )
