"""Model providers.

Import a role factory rather than a concrete provider, so the choice of model
stays in one place. Each role reads exactly one setting and builds exactly that
provider: there is no fallback, silent or otherwise. A role whose provider has
no key gets a provider that reports itself unconfigured and fails with
`ModelNotConfiguredError` - never a different vendor.
"""

from __future__ import annotations

from app.models.provider import AnalysisRequest, ModelProvider, QuestionRequest

__all__ = [
    "AnalysisRequest",
    "ModelProvider",
    "QuestionRequest",
    "build_provider",
    "get_analysis_provider",
    "get_model_provider",
    "get_qa_provider",
    "get_reasoning_provider",
]


def build_provider(name: str) -> ModelProvider:
    """The provider called `name`. Raises on an unknown name."""
    if name == "gemini":
        from app.models.gemini import GeminiProvider

        return GeminiProvider()
    if name == "nemotron":
        from app.models.nemotron import NemotronProvider

        return NemotronProvider()
    raise ValueError(f"unknown provider: {name!r}")


def get_analysis_provider() -> ModelProvider:
    """The provider configured by ANALYSIS_PROVIDER."""
    from app.core.config import get_settings

    return build_provider(get_settings().analysis_provider)


def get_qa_provider() -> ModelProvider:
    """The provider configured by QA_PROVIDER."""
    from app.core.config import get_settings

    return build_provider(get_settings().qa_provider)


def get_reasoning_provider():
    """The reasoning provider, or None when reasoning is switched off.

    Off means REASONING_ENABLED=false or REASONING_PROVIDER=none; either wins.
    A provider that is on but has no key is still returned, so the stage can
    record `unavailable/configuration` rather than silently not running.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.reasoning_effective:
        return None
    if settings.reasoning_provider == "nemotron":
        from app.models.nemotron import NemotronProvider

        return NemotronProvider()
    return None


#: The pre-Phase-23 name for the analysis factory. Kept because it is the seam
#: the runner and many tests patch.
get_model_provider = get_analysis_provider
