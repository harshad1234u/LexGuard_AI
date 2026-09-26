"""Health endpoint (docs/07_API_SPEC.md)."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.documents import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "0.2.0"


@router.get("/ready")
def ready() -> dict:
    """Per-role readiness. Booleans and provider names only - never a key."""
    from app.persistence import get_repository

    settings = get_settings()
    return {
        "status": "ok",
        "providers": {
            "analysis": settings.analysis_provider,
            "qa": settings.qa_provider,
            "reasoning": settings.reasoning_provider if settings.reasoning_effective else "none",
        },
        "configured": settings.provider_readiness(),
        "persistence_enabled": bool(get_repository().enabled),
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=VERSION,
        # A boolean only. The key itself must never leave the server.
        model_provider_configured=settings.model_configured,
    )
