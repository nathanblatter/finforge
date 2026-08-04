"""Bug report router — forwards user-submitted bugs to the flightdeck board.

The flightdeck ingest key lives only on the server, so it never ships in the
client bundle. The browser calls this same-origin endpoint; we forward to
flightdeck over the shared docker network.
"""

import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from config import settings
from dependencies import verify_api_key

logger = logging.getLogger("finforge.api.bug_report")

router = APIRouter(tags=["bug-report"])

_SITE = "finforge"
_VALID_SEVERITY = {"low", "med", "high", "urgent"}

# Screenshot limits — mirror flightdeck's server-side caps so we can fail fast
# with a friendly error instead of a 502 from the upstream.
_MAX_SCREENSHOTS = 4
_MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024  # 8MB each
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


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

    item_id: Optional[str] = None
    try:
        item_id = resp.json().get("id")
    except ValueError:
        logger.warning("flightdeck ingest returned non-JSON body; no item id available")

    return {"ok": True, "item_id": item_id}


@router.post("/bug-report/{item_id}/screenshots", status_code=201)
async def upload_bug_screenshots(
    item_id: str,
    files: list[UploadFile] = File(...),
    _=Depends(verify_api_key),
):
    """Forward bug-report screenshots to flightdeck's attachment endpoint.

    The ingest key stays server-side; the browser only ever talks to us.
    Flightdeck re-validates everything (magic-byte sniffing, item age/source),
    but we enforce the count/size/type caps here for fast, friendly errors.
    """
    if not settings.flightdeck_ingest_key:
        raise HTTPException(status_code=503, detail="Bug reporting is not configured.")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > _MAX_SCREENSHOTS:
        raise HTTPException(
            status_code=400, detail=f"At most {_MAX_SCREENSHOTS} screenshots per report."
        )

    parts = []
    for f in files:
        if f.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Only PNG, JPEG, WebP, or GIF images are accepted.",
            )
        data = await f.read()
        if len(data) > _MAX_SCREENSHOT_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Each screenshot must be under {_MAX_SCREENSHOT_BYTES // (1024 * 1024)}MB.",
            )
        parts.append(("files", (f.filename or "screenshot.png", data, f.content_type)))

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.flightdeck_url.rstrip('/')}/api/ingest/attachments/{item_id}",
                files=parts,
                headers={"X-API-Key": settings.flightdeck_ingest_key},
            )
    except httpx.RequestError as exc:
        logger.error("flightdeck attachment upload unreachable: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach the bug tracker.")

    if resp.status_code >= 300:
        logger.error(
            "flightdeck attachment upload failed: status=%s body=%s",
            resp.status_code,
            resp.text,
        )
        raise HTTPException(status_code=502, detail="Bug tracker rejected the screenshots.")

    return {"ok": True, "attachments": resp.json()}
