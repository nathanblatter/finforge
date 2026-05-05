"""Shared FastAPI dependencies for FinForge."""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify X-API-Key header against the configured API key.
    Required on all endpoints — NateBot and service-to-service auth.
    """
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
