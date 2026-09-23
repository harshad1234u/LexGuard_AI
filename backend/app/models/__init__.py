"""Model providers.

Import `get_model_provider()` rather than a concrete provider, so the choice of
model stays in one place.
"""

from __future__ import annotations

from app.models.provider import AnalysisRequest, ModelProvider, QuestionRequest

__all__ = [
    "AnalysisRequest",
    "ModelProvider",
    "QuestionRequest",
    "get_model_provider",
]


def get_model_provider() -> ModelProvider:
    """The configured provider.

    One decision point. When a second provider exists (a fallback, or a
    different vendor), it is selected here and nothing upstream changes.
    """
    from app.models.nemotron import NemotronProvider

    return NemotronProvider()
