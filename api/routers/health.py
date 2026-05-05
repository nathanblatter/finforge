"""Health-check router for FinForge API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings
from database import check_db_connection
from schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# ---------------------------------------------------------------------------
# API-key security scheme
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: Annotated[str | None, Security(_api_key_header)]) -> str:
    """Dependency that validates the X-API-Key header."""
    if api_key is None or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description=(
        "Returns the current health status of the API, database connectivity, "
        "and the timestamps of the most recent data syncs."
    ),
)
def get_health(
    _: Annotated[str, Depends(verify_api_key)],
) -> HealthResponse:
    """Check API and database health."""
    db_ok = check_db_connection()

    if not db_ok:
        logger.warning("Health check: database connection failed.")

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version="1.0.0",
        environment=settings.environment,
        db_connected=db_ok,
        last_plaid_sync=None,   # populated in Phase 2 once sync jobs run
        last_schwab_sync=None,  # populated in Phase 2 once sync jobs run
    )
