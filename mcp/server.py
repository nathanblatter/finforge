"""FinForge MCP server — read-only financial tools for agents.

Thin wrapper over the FinForge REST API (mirrors the flightdeck pattern:
streamable-HTTP MCP bound to the tailnet). Consumers: natebot's brain
sessions and any Claude Code / claude.ai agent on the tailnet.

Read-only by design: write routes (dismiss anomaly, mark-legit, rules)
stay out until the read surface proves itself.
"""

import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

API_URL = os.getenv("FINFORGE_API_URL", "http://finforge-api:8000/api/v1")
API_KEY = os.getenv("FINFORGE_API_KEY", "")

mcp = MCPServer("finforge")

_client = httpx.AsyncClient(
    base_url=API_URL,
    headers={"X-API-Key": API_KEY},
    timeout=30.0,
)


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    resp = await _client.get(path, params=params)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    return resp.json() if ctype.startswith("application/json") else resp.text


@mcp.tool()
async def get_summary() -> Any:
    """Full financial state snapshot: balances, net worth, accounts."""
    return await _get("/summary")


@mcp.tool()
async def get_briefing() -> Any:
    """Pre-formatted daily financial briefing (net worth, portfolio risk, alerts) as readable text."""
    return await _get("/natebot/imessage/briefing")


@mcp.tool()
async def get_portfolio() -> Any:
    """Current investment portfolio: positions, allocation, risk — as readable text."""
    return await _get("/natebot/imessage/portfolio")


@mcp.tool()
async def get_financial_goals() -> Any:
    """Financial goals and progress toward them, as readable text."""
    return await _get("/natebot/imessage/goals")


@mcp.tool()
async def get_watchlist() -> Any:
    """Stock watchlist with current prices, as readable text."""
    return await _get("/natebot/imessage/watchlist")


@mcp.tool()
async def spending_monthly(month: str | None = None) -> Any:
    """Monthly spending breakdown by category. month: 'YYYY-MM', defaults to current month."""
    return await _get("/spending/monthly", {"month": month})


@mcp.tool()
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


@mcp.tool()
async def search_transactions(q: str) -> Any:
    """Full-text search over transactions (merchant names, descriptions)."""
    return await _get("/spending/search", {"q": q})


@mcp.tool()
async def merchant_spending(name: str) -> Any:
    """Spending history and stats for a single merchant."""
    return await _get("/spending/merchant", {"name": name})


@mcp.tool()
async def get_subscriptions(months: int | None = None) -> Any:
    """Detected recurring subscriptions over the lookback window (months)."""
    return await _get("/spending/subscriptions", {"months": months})


@mcp.tool()
async def spending_forecast(months: int | None = None) -> Any:
    """Forward spending forecast including upcoming bills."""
    return await _get("/spending/forecast", {"months": months})


@mcp.tool()
async def get_anomalies(include_dismissed: bool | None = None, limit: int | None = None) -> Any:
    """Unusual-spending anomalies flagged by FinForge."""
    return await _get("/spending/anomalies", {"include_dismissed": include_dismissed, "limit": limit})


@mcp.tool()
async def charge_guardian(status: str | None = None, kind: str | None = None, limit: int | None = None) -> Any:
    """Charge-guardian findings: suspicious/duplicate/price-hike charges needing review."""
    return await _get("/spending/charge-guardian", {"status": status, "kind": kind, "limit": limit})


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        stateless_http=True,
        json_response=True,
    )
