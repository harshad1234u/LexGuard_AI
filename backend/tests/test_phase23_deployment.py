"""Phase 23: deployment configuration stays consistent with the code.

One source of truth for configuration is `Settings`. These tests fail when an
example file, the Render blueprint or the Vercel config drifts from it, or
when a secret gains a value in a committed file.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.core.config import Settings, get_settings

ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRETS = {"GEMINI_API_KEY", "NVIDIA_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "PERSISTENCE_HASH_SALT"}


def env_example() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.split("#", 1)[0].strip()
    return values


def setting_names() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


class TestEnvExample:
    def test_every_example_key_is_a_real_setting(self):
        unknown = set(env_example()) - setting_names()
        assert not unknown, f"documented but not read by the app: {unknown}"

    def test_every_setting_is_documented(self):
        missing = setting_names() - set(env_example())
        assert not missing, f"read by the app but not documented: {missing}"

    def test_no_secret_has_a_value_in_the_example(self):
        example = env_example()
        for key in SECRETS:
            assert example[key] == "", f"{key} must be empty in .env.example"

    def test_the_example_itself_is_a_valid_configuration(self, monkeypatch):
        for key, value in env_example().items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        settings = Settings(_env_file=None)
        assert settings.analysis_provider == "gemini"
        assert settings.gemini_model == "gemini-3.8-flash"

    def test_the_frontend_example_holds_only_the_api_origin(self):
        text = (ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
        keys = re.findall(r"^([A-Z_]+)=", text, flags=re.MULTILINE)
        assert keys == ["VITE_API_BASE_URL"]


class TestRenderBlueprint:
    yaml = pytest.importorskip("yaml")

    def blueprint(self):
        return self.yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))

    def test_one_instance_of_the_docker_backend(self):
        [service] = self.blueprint()["services"]
        assert service["runtime"] == "docker"
        assert service["numInstances"] == 1, "state is in process memory"
        assert service["healthCheckPath"] == "/api/v1/health"

    def test_env_keys_are_real_settings_and_secrets_have_no_value(self):
        [service] = self.blueprint()["services"]
        for entry in service["envVars"]:
            assert entry["key"] in setting_names(), entry["key"]
            if entry["key"] in SECRETS:
                assert entry.get("sync") is False and "value" not in entry, entry["key"]


class TestVercelConfig:
    def test_spa_rewrite_and_bundle_check(self):
        config = json.loads((ROOT / "frontend" / "vercel.json").read_text(encoding="utf-8"))
        assert config["outputDirectory"] == "dist"
        assert "check:bundle" in config["buildCommand"]
        assert {"source": "/(.*)", "destination": "/index.html"} in config["rewrites"]

    def test_no_server_secret_is_referenced_by_frontend_source(self):
        source = ROOT / "frontend" / "src"
        for path in source.rglob("*.ts*"):
            text = path.read_text(encoding="utf-8")
            for key in SECRETS | {"SUPABASE_URL", "service_role"}:
                assert key not in text, f"{key} referenced in {path.name}"
            for match in re.findall(r"import\.meta\.env\.(\w+)", text):
                assert match == "VITE_API_BASE_URL", f"{match} in {path.name}"


class TestCors:
    def test_a_vercel_origin_is_accepted_exactly(self, monkeypatch, client):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://lexguard.vercel.app")
        get_settings.cache_clear()
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()) as c:
            ok = c.get("/api/v1/health", headers={"Origin": "https://lexguard.vercel.app"})
            other = c.get("/api/v1/health", headers={"Origin": "https://evil.example"})
        assert ok.headers.get("access-control-allow-origin") == "https://lexguard.vercel.app"
        assert "access-control-allow-origin" not in other.headers
