"""Bug report router — forwards user-submitted bugs to the flightdeck board.

The flightdeck ingest key lives only on the server, so it never ships in the
client bundle. The browser calls this same-origin endpoint; we forward to
flightdeck over the shared docker network.
"""

import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from config import settings
from dependencies import verify_api_key

logger = logging.getLogger("finforge.api.bug_report")

router = APIRouter(tags=["bug-report"])

_SITE = "finforge"
_VALID_SEVERITY = {"low", "med", "high", "urgent"}


class BugReportBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    severity: str = "med"
    url: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


@router.post("/bug-report")
async def submit_bug_report(body: BugReportBody, _=Depends(verify_api_key)):
    if not settings.flightdeck_ingest_key:
        raise HTTPException(status_code=503, detail="Bug reporting is not configured.")

    severity = body.severity if body.severity in _VALID_SEVERITY else "med"
    payload = {
        "site": _SITE,
        "url": body.url or "",
        "message": body.message.strip(),
        "severity": severity,
        "meta": body.meta or {},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.flightdeck_url.rstrip('/')}/api/ingest/bug",
                json=payload,
                headers={"X-API-Key": settings.flightdeck_ingest_key},
            )
    except httpx.RequestError as exc:
        logger.error("flightdeck ingest unreachable: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach the bug tracker.")

    if resp.status_code >= 300:
        logger.error("flightdeck ingest failed: status=%s body=%s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="Bug tracker rejected the report.")

    return {"ok": True}
