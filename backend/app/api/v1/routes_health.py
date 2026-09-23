"""Health endpoint (docs/07_API_SPEC.md)."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.documents import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "0.2.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=VERSION,
        # A boolean only. The key itself must never leave the server.
        model_provider_configured=settings.model_configured,
    )
