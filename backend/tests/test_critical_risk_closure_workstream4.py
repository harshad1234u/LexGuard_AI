"""Workstream 4: Provider timeout, concurrent requests, and reliability audit tests.

Verifies:
1. Forced provider timeouts result in safe terminal failures without leaking state.
2. The API server remains responsive during and after repeated provider timeouts.
3. Timed-out operations cannot later mutate or release findings into completed results.
4. Active tasks in AnalysisRunner are cleanly reclaimed without thread or task leaks.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import pytest
from fastapi.testclient import TestClient

from app.agents.runner import AnalysisJob, analysis_runner
from app.core.config import get_settings
from app.models.errors import ModelTimeoutError
from app.models.gemini import GeminiProvider
from app.models.payload import DocumentPayload
from app.models.provider import AnalysisRequest, ModelProvider
from app.schemas.analysis import AnalysisStage, AnalysisStatus, ErrorCategory
from app.schemas.findings import Finding, ModelAnalysis
from tests.conftest import make_pdf, upload
from tests.test_workflow import PAGE_TEXT, TRUE_FINDING, single_page_pdf


class StalledProvider(ModelProvider):
    """A model provider that deliberately hangs past any reasonable deadline."""

    name = "stalled"
    model_id = "stalled-v1"

    @property
    def is_configured(self) -> bool:
        return True

    def __init__(self, delay: float = 10.0):
        self.delay = delay
        self.finished = threading.Event()
        self.invocation_count = 0

    async def analyze_document(self, request: AnalysisRequest) -> ModelAnalysis:
        self.invocation_count += 1
        await asyncio.sleep(self.delay)
        self.finished.set()
        return ModelAnalysis(
            findings=[
                Finding(
                    type="clause",
                    claim="The Supplier shall maintain insurance of $1,000,000.",
                    evidence_page=1,
                    evidence_quote="shall maintain insurance of $1,000,000",
                    category="liability",
                )
            ]
        )

    async def answer_question(self, request):
        await asyncio.sleep(self.delay)
        raise ModelTimeoutError("Timeout in QA")


@pytest.fixture
def fast_timeout_env(monkeypatch):
    """Set 1-second timeout bounds so tests run quickly without blocking."""
    monkeypatch.setenv("ANALYSIS_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("MODEL_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestTimeoutReliability:
    """Verifies server responsiveness and immutability under forced timeouts."""

    def test_forced_timeout_transitions_to_failed_with_null_result(
        self, client: TestClient, fast_timeout_env, monkeypatch
    ):
        stalled = StalledProvider(delay=3.0)
        from app.models import get_model_provider
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: stalled)

        doc_resp = upload(client, single_page_pdf())
        assert doc_resp.status_code == 201
        doc_id = doc_resp.json()["document_id"]

        start_resp = client.post(f"/api/v1/documents/{doc_id}/analyze")
        assert start_resp.status_code == 202
        analysis_id = start_resp.json()["analysis_id"]

        # Wait for terminal failure
        deadline = time.time() + 5.0
        terminal_status = None
        while time.time() < deadline:
            poll_resp = client.get(f"/api/v1/analysis/{analysis_id}/status")
            data = poll_resp.json()
            if data["status"] in {"completed", "failed"}:
                terminal_status = data
                break
            time.sleep(0.05)

        assert terminal_status is not None, "Analysis failed to reach terminal status"
        assert terminal_status["status"] == "failed"
        assert terminal_status["error_category"] in {
            ErrorCategory.ANALYSIS_TIMEOUT,
            ErrorCategory.PROVIDER_TIMEOUT,
        }
        # Guarantee no findings released under timeout
        assert terminal_status.get("result") is None

    def test_server_remains_responsive_during_and_after_repeated_timeouts(
        self, client: TestClient, fast_timeout_env, monkeypatch
    ):
        stalled = StalledProvider(delay=2.0)
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: stalled)

        # Upload first doc and trigger timeout
        doc1 = upload(client, make_pdf(pages=2)).json()["document_id"]
        client.post(f"/api/v1/documents/{doc1}/analyze")

        # Concurrently, another request comes in: health/upload should succeed immediately
        doc2_resp = upload(client, make_pdf(pages=1, text="The fee is Rs 50,000 payable within 15 days."))
        assert doc2_resp.status_code == 201
        doc2_id = doc2_resp.json()["document_id"]

        # Run extraction on doc2
        extract_resp = client.post(f"/api/v1/documents/{doc2_id}/extract")
        assert extract_resp.status_code == 200

        # Value index extraction (purely deterministic) must respond immediately even while doc1 is timing out
        values_resp = client.get(f"/api/v1/documents/{doc2_id}/values")
        assert values_resp.status_code == 200
        assert "values" in values_resp.json()

        # Repeat with doc2: trigger another timeout
        client.post(f"/api/v1/documents/{doc2_id}/analyze")

        # Third doc upload still responds 201
        doc3_resp = upload(client, make_pdf(pages=1, text="Third document responsiveness check."))
        assert doc3_resp.status_code == 201

    def test_timed_out_operation_cannot_later_mutate_results(
        self, client: TestClient, fast_timeout_env, monkeypatch
    ):
        stalled = StalledProvider(delay=1.5)
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: stalled)

        doc_resp = upload(client, single_page_pdf())
        doc_id = doc_resp.json()["document_id"]

        start_resp = client.post(f"/api/v1/documents/{doc_id}/analyze")
        analysis_id = start_resp.json()["analysis_id"]

        # Wait until it is marked failed by timeout (1.0s timeout)
        time.sleep(1.2)
        status_after_timeout = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        assert status_after_timeout["status"] == "failed"

        # Now wait for the delayed background provider to complete (1.5s delay)
        time.sleep(1.0)

        # Verify that late completion did NOT mutate the job to completed
        status_later = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        assert status_later["status"] == "failed"
        assert status_later.get("result") is None
        assert status_later.get("verified_count") is None

    def test_runner_tasks_are_cleared_after_failure(
        self, client: TestClient, fast_timeout_env, monkeypatch
    ):
        stalled = StalledProvider(delay=1.5)
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: stalled)

        doc_resp = upload(client, single_page_pdf())
        doc_id = doc_resp.json()["document_id"]

        start_resp = client.post(f"/api/v1/documents/{doc_id}/analyze")
        analysis_id = start_resp.json()["analysis_id"]

        # Wait for failure and task callback cleanup
        time.sleep(1.4)
        assert analysis_id not in analysis_runner._tasks
