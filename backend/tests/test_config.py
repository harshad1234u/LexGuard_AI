"""Configuration loading.

These guard two things that failed silently before: a `.env` placed at the repo
root being ignored, and list-valued settings written in the natural
comma-separated form being rejected.
"""

from __future__ import annotations

import pytest

from app.core.config import ENV_FILES, Settings, get_settings


class TestEnvFileDiscovery:
    def test_both_repo_root_and_backend_env_are_searched(self):
        names = [f.parent.name for f in ENV_FILES]
        assert "backend" in names
        # The repo root is the other candidate.
        assert len(ENV_FILES) == 2

    def test_backend_env_takes_precedence_over_repo_root(self):
        """Later files win, so a backend-local .env can override the shared one."""
        assert ENV_FILES[-1].parent.name == "backend"


class TestAllowedOrigins:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("http://localhost:5173", ["http://localhost:5173"]),
            (
                "http://localhost:5173,https://app.example",
                ["http://localhost:5173", "https://app.example"],
            ),
            ("  http://a.test , http://b.test  ", ["http://a.test", "http://b.test"]),
            ("", []),
        ],
    )
    def test_comma_separated_origins_are_parsed(self, raw, expected, monkeypatch):
        """A .env holds plain text, not JSON - the natural form must work."""
        monkeypatch.setenv("ALLOWED_ORIGINS", raw)
        get_settings.cache_clear()
        assert Settings().allowed_origins == expected

    def test_json_list_form_still_works(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", '["http://a.test","http://b.test"]')
        get_settings.cache_clear()
        assert Settings().allowed_origins == ["http://a.test", "http://b.test"]


class TestSecretHandling:
    def test_model_configured_is_a_boolean_not_the_key(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-not-a-real-key")
        get_settings.cache_clear()
        settings = Settings()

        assert settings.model_configured is True
        assert isinstance(settings.model_configured, bool)

    def test_absent_key_reports_not_configured(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "")
        get_settings.cache_clear()
        assert Settings().model_configured is False

    def test_health_response_never_carries_the_key(self, client, monkeypatch):
        """Guards the whole response body, not just the one field."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-canary-value-do-not-leak")
        get_settings.cache_clear()

        response = client.get("/api/v1/health")
        assert "nvapi-canary-value-do-not-leak" not in response.text
        assert "nvapi" not in response.text
