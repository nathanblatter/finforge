"""Global exception handling and request logging middleware."""

import logging
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("finforge.api.middleware")


async def _error_handling_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.error(
            "Unhandled exception on %s %s [request_id=%s]\n%s",
            request.method, request.url.path, request_id, traceback.format_exc(),
        )
        response = JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": "Check server logs for request_id."},
        )

    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s — status=%d duration=%.1fms request_id=%s",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    return response


def register_middleware(app: FastAPI) -> None:
    app.middleware("http")(_error_handling_middleware)
