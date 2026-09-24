"""Where a result came from (Phase 23).

Recorded on every analysis result and every answer, and persisted beside them
when persistence is enabled. Names and versions only: never a prompt, a key, or
anything the model wrote.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Which provider produced a result, and which policy released it."""

    provider: str = Field(description="The analysis or Q&A provider actually called.")
    model: str = Field(description="The model identifier that provider was configured with.")
    reasoning_provider: str | None = Field(
        default=None,
        description="Null when reasoning was not effective. Always null for answers.",
    )
    reasoning_model: str | None = None
    verification_policy_version: str = Field(
        description="The release rules applied. The model never decides verification."
    )
    status: str


def provider_identity(provider) -> tuple[str, str]:
    """(name, model) for any provider, including test fakes without a model id."""
    name = str(getattr(provider, "name", "") or "unknown")
    model = str(getattr(provider, "model_id", "") or "unknown")
    return name, model
