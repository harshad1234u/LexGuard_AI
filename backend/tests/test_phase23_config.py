"""Phase 23: provider-role configuration.

One canonical model: ANALYSIS_PROVIDER, QA_PROVIDER, REASONING_PROVIDER and the
REASONING_ENABLED master switch. Unknown values refuse to start; a missing key
is not fatal but makes that role report not-configured; nothing ever falls
back to another provider.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.models import (
    get_analysis_provider,
    get_model_provider,
    get_qa_provider,
    get_reasoning_provider,
)
from app.models.errors import ModelNotConfiguredError
from app.models.gemini import GeminiProvider
from app.models.nemotron import NemotronProvider
from app.models.payload import DocumentPayload
from app.models.provider import AnalysisRequest

GEMINI_CANARY = "AIza-canary-gemini-key-do-not-leak-000"
NVIDIA_CANARY = "nvapi-canary-phase23-do-not-leak-000"
SUPABASE_CANARY = "sb-service-role-canary-do-not-leak-000"


def settings(monkeypatch, **env) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key.upper(), value)
    get_settings.cache_clear()
    return Settings()


class TestDefaults:
    def test_product_defaults_are_gemini_gemini_nemotron(self, monkeypatch):
        """The test suite pins nemotron roles; the product default is Gemini."""
        for key in ("ANALYSIS_PROVIDER", "QA_PROVIDER", "REASONING_PROVIDER", "REASONING_ENABLED"):
            monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)
        assert (s.analysis_provider, s.qa_provider, s.reasoning_provider) == (
            "gemini",
            "gemini",
            "nemotron",
        )
        assert s.reasoning_enabled is True

    def test_there_is_no_built_in_gemini_model_name(self, monkeypatch):
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        assert Settings.model_fields["gemini_model"].default is None


class TestValidation:
    @pytest.mark.parametrize(
        "key,value",
        [
            ("ANALYSIS_PROVIDER", "openai"),
            ("QA_PROVIDER", "claude"),
            ("REASONING_PROVIDER", "gemini"),
            ("APP_ENV", "staging"),
        ],
    )
    def test_unknown_role_values_refuse_to_start(self, monkeypatch, key, value):
        with pytest.raises(ValidationError):
            settings(monkeypatch, **{key: value})

    @pytest.mark.parametrize("role", ["ANALYSIS_PROVIDER", "QA_PROVIDER"])
    def test_a_gemini_role_without_a_model_refuses_to_start(self, monkeypatch, role):
        with pytest.raises(ValidationError, match="GEMINI_MODEL"):
            settings(monkeypatch, **{role: "gemini", "GEMINI_MODEL": ""})

    def test_nemotron_roles_do_not_need_a_gemini_model(self, monkeypatch):
        s = settings(monkeypatch, GEMINI_MODEL="")
        assert s.analysis_provider == "nemotron"

    def test_a_validation_error_never_echoes_a_key(self, monkeypatch):
        """Pydantic would otherwise print a truncated key in input_value."""
        with pytest.raises(ValidationError) as caught:
            settings(
                monkeypatch,
                NVIDIA_API_KEY=NVIDIA_CANARY,
                GEMINI_API_KEY=GEMINI_CANARY,
                ANALYSIS_PROVIDER="gemini",
                GEMINI_MODEL="",
            )
        text = str(caught.value)
        for fragment in ("nvapi", "AIza", NVIDIA_CANARY[:12], GEMINI_CANARY[:10]):
            assert fragment not in text


class TestReasoningSwitch:
    @pytest.mark.parametrize(
        "enabled,provider,effective",
        [
            ("true", "nemotron", True),
            ("true", "none", False),
            ("false", "nemotron", False),
            ("false", "none", False),
        ],
    )
    def test_either_switch_off_wins(self, monkeypatch, enabled, provider, effective):
        s = settings(monkeypatch, REASONING_ENABLED=enabled, REASONING_PROVIDER=provider)
        assert s.reasoning_effective is effective
        assert (get_reasoning_provider() is not None) is effective


class TestReadiness:
    def test_readiness_is_booleans_per_role(self, monkeypatch):
        s = settings(
            monkeypatch,
            ANALYSIS_PROVIDER="gemini",
            QA_PROVIDER="nemotron",
            REASONING_ENABLED="true",
            GEMINI_API_KEY=GEMINI_CANARY,
            NVIDIA_API_KEY="",
        )
        assert s.provider_readiness() == {"analysis": True, "qa": False, "reasoning": False}
        assert s.model_configured is True

    def test_persistence_needs_url_and_key_and_in_production_a_salt(self, monkeypatch):
        s = settings(monkeypatch, SUPABASE_URL="https://x.supabase.co",
                     SUPABASE_SERVICE_ROLE_KEY=SUPABASE_CANARY)
        assert s.persistence_configured is True
        s = settings(monkeypatch, APP_ENV="production", PERSISTENCE_HASH_SALT="")
        assert s.persistence_configured is False
        s = settings(monkeypatch, PERSISTENCE_HASH_SALT="pepper")
        assert s.persistence_configured is True
        s = settings(monkeypatch, SUPABASE_SERVICE_ROLE_KEY="")
        assert s.persistence_configured is False

    def test_repr_of_settings_carries_no_secret(self, monkeypatch):
        s = settings(
            monkeypatch,
            GEMINI_API_KEY=GEMINI_CANARY,
            NVIDIA_API_KEY=NVIDIA_CANARY,
            SUPABASE_SERVICE_ROLE_KEY=SUPABASE_CANARY,
            PERSISTENCE_HASH_SALT="salt-canary-value",
        )
        text = repr(s) + str(s)
        for canary in (GEMINI_CANARY, NVIDIA_CANARY, SUPABASE_CANARY, "salt-canary-value"):
            assert canary not in text

    def test_ready_endpoint_reports_booleans_and_names_only(self, client, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", GEMINI_CANARY)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_CANARY)
        get_settings.cache_clear()
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"status", "providers", "configured", "persistence_enabled"}
        assert all(isinstance(v, bool) for v in body["configured"].values())
        for canary in (GEMINI_CANARY, SUPABASE_CANARY, "AIza", "nvapi"):
            assert canary not in response.text


class TestFactoriesNeverFallBack:
    def test_each_role_builds_exactly_its_configured_provider(self, monkeypatch):
        settings(monkeypatch, ANALYSIS_PROVIDER="gemini", QA_PROVIDER="nemotron")
        assert isinstance(get_analysis_provider(), GeminiProvider)
        assert isinstance(get_model_provider(), GeminiProvider)
        assert isinstance(get_qa_provider(), NemotronProvider)

        settings(monkeypatch, ANALYSIS_PROVIDER="nemotron", QA_PROVIDER="gemini")
        assert isinstance(get_analysis_provider(), NemotronProvider)
        assert isinstance(get_qa_provider(), GeminiProvider)

    async def test_gemini_without_a_key_fails_as_not_configured_not_as_nemotron(
        self, monkeypatch
    ):
        """The NVIDIA key is present and Gemini's is not: still no fallback."""
        settings(
            monkeypatch,
            ANALYSIS_PROVIDER="gemini",
            GEMINI_API_KEY="",
            NVIDIA_API_KEY=NVIDIA_CANARY,
        )
        provider = get_analysis_provider()
        assert isinstance(provider, GeminiProvider)
        assert provider.is_configured is False
        payload = DocumentPayload(document_id="doc_x", total_pages=0)
        with pytest.raises(ModelNotConfiguredError):
            await provider.analyze_document(AnalysisRequest(payload=payload))

    def test_the_analysis_api_reports_the_missing_gemini_key(self, client, monkeypatch):
        """End to end: a Gemini role with no key is a clean provider_not_configured."""
        from tests.conftest import upload
        from tests.test_api_analysis import wait_for_terminal
        from tests.test_workflow import single_page_pdf

        settings(monkeypatch, ANALYSIS_PROVIDER="gemini", NVIDIA_API_KEY=NVIDIA_CANARY)
        document_id = upload(client, single_page_pdf()).json()["document_id"]
        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        body = wait_for_terminal(client, analysis_id)
        assert body["status"] == "failed"
        assert body["error_category"] == "provider_not_configured"
