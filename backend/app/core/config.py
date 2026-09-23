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

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_*` are our own config fields, not pydantic model attributes.
        protected_namespaces=(),
    )

    # --- Model provider ------------------------------------------------
    nvidia_api_key: str | None = None
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

    @property
    def model_configured(self) -> bool:
        return bool(self.nvidia_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
