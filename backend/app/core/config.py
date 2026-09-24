"""Application configuration.

Secrets are loaded from the environment only (04_SECURITY_GROUNDING.md sec. 8).
Nothing here is ever serialised to an API response.
"""

from functools import lru_cache
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent

#: Checked in order; later files win, so a backend-local .env overrides the
#: shared one at the repo root. Supporting both means the key can live wherever
#: the developer put it without silently falling back to "not configured".
ENV_FILES = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_*` are our own config fields, not pydantic model attributes.
        protected_namespaces=(),
        # A validation error otherwise echoes every input value - including a
        # truncated API key - into the exception text and so into startup logs.
        hide_input_in_errors=True,
    )

    # --- Provider roles (Phase 23) --------------------------------------
    # One setting per responsibility. Validated at startup; an unknown value
    # refuses to start. There is no fallback: a role only ever calls the
    # provider named here (docs/12_DEPLOYMENT.md, "Provider configuration").
    analysis_provider: Literal["gemini", "nemotron"] = "gemini"
    qa_provider: Literal["gemini", "nemotron"] = "gemini"
    reasoning_provider: Literal["nemotron", "none"] = "nemotron"
    # Master switch. Reasoning runs only if this is true AND the provider is
    # not "none"; either one saying off wins, so no combination contradicts.
    reasoning_enabled: bool = True
    reasoning_timeout_seconds: int = 90

    # --- Gemini ---------------------------------------------------------
    gemini_api_key: str | None = Field(default=None, repr=False)
    # No built-in default: a model name is a deployment decision, verified
    # against the provider's current catalogue, never assumed by the code.
    gemini_model: str | None = None

    # --- NVIDIA -----------------------------------------------------------
    nvidia_api_key: str | None = Field(default=None, repr=False)
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
    model_temperature: float = 0.6
    model_top_p: float = 0.95
    model_max_output_tokens: int = 20480
    model_timeout_seconds: int = 180

    # --- Workflow ------------------------------------------------------
    # A whole-run budget, above the provider's per-call timeout. Generous by
    # design: a long document is several model-minutes, and cutting a run
    # short wastes the inference already paid for.
    analysis_timeout_seconds: int = 900

    # --- Q&A ------------------------------------------------------------
    # Q&A is synchronous: one question, one short answer, a user waiting for
    # it. The budget is therefore shorter than the analysis provider timeout,
    # so a stuck call fails while the request is still worth answering rather
    # than holding a connection open for three minutes.
    qa_timeout_seconds: int = 120

    # --- Upload limits -------------------------------------------------
    max_upload_bytes: int = 25 * 1024 * 1024
    max_pages: int = 300

    # Cap on a JSON request body, checked before the body is parsed. Uploads
    # are multipart and keep their own, much larger, streaming limit. 64 KiB is
    # far more than the 2000-character question the only JSON endpoint takes,
    # and far less than something worth parsing to find that out.
    max_json_body_bytes: int = 64 * 1024

    # --- Ephemeral processing -----------------------------------------
    temp_workspace_dir: str | None = None
    document_ttl_seconds: int = 3600

    # --- API ------------------------------------------------------------
    # NoDecode stops pydantic-settings from JSON-decoding this before the
    # validator below runs, so a plain comma-separated .env value works.
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    log_level: str = "INFO"
    app_env: Literal["development", "production"] = "development"

    # --- Optional metadata persistence (Supabase, backend only) -----------
    # Unset means in-memory only, which is the default and the test mode.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = Field(default=None, repr=False)
    persistence_hash_salt: str | None = Field(default=None, repr=False)
    supabase_retention_days: int = Field(default=30, ge=1, le=365)

    @model_validator(mode="after")
    def _gemini_needs_a_model(self) -> "Settings":
        """A role set to Gemini with no model name refuses to start.

        The key may be missing - that role then reports not-configured at
        request time - but a model name is never guessed.
        """
        uses_gemini = "gemini" in (self.analysis_provider, self.qa_provider)
        if uses_gemini and not (self.gemini_model or "").strip():
            raise ValueError(
                "GEMINI_MODEL must be set when ANALYSIS_PROVIDER or QA_PROVIDER is gemini"
            )
        return self

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON array.

        `NoDecode` hands us the raw string, so both forms are handled here: a
        .env is most naturally written as `a,b`, while JSON is what
        pydantic-settings documents. Supporting only one would make a
        reasonable-looking config silently wrong.
        """
        if not isinstance(value, str):
            return value

        text = value.strip()
        if text.startswith("["):
            import json

            try:
                return json.loads(text)
            except ValueError:
                # Fall through and treat it as a plain string.
                pass

        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @property
    def workspace_path(self) -> Path:
        """Root directory for ephemeral per-document working files."""
        if self.temp_workspace_dir:
            return Path(self.temp_workspace_dir)
        return Path(__file__).resolve().parents[2] / ".workspace"

    def provider_key_present(self, provider: str) -> bool:
        """Whether the named provider has a key. A boolean, never the key."""
        if provider == "gemini":
            return bool(self.gemini_api_key)
        if provider == "nemotron":
            return bool(self.nvidia_api_key)
        return False

    @property
    def reasoning_effective(self) -> bool:
        """Whether the reasoning stage is switched on at all."""
        return self.reasoning_enabled and self.reasoning_provider != "none"

    @property
    def persistence_configured(self) -> bool:
        """Supabase credentials present, and a salt when in production."""
        if not (self.supabase_url and self.supabase_service_role_key):
            return False
        if self.app_env == "production" and not self.persistence_hash_salt:
            return False
        return True

    def provider_readiness(self) -> dict[str, bool]:
        """Per-role readiness, as booleans only."""
        return {
            "analysis": self.provider_key_present(self.analysis_provider),
            "qa": self.provider_key_present(self.qa_provider),
            "reasoning": self.reasoning_effective
            and self.provider_key_present(self.reasoning_provider),
        }

    @property
    def model_configured(self) -> bool:
        """Whether the selected *analysis* provider has its key."""
        return self.provider_key_present(self.analysis_provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
