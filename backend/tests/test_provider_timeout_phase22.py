"""Phase 22: provider timeout and cancellation.

The defect: `ChatNVIDIA(...)` lists the hosted models over a blocking HTTP
request with no socket timeout, and the client was built on the event loop,
before the provider's deadline started. A stalled listing froze the whole
server - the 180 s provider timeout and the 900 s workflow budget included -
and left no provider log line.

Every stall here waits on a `threading.Event` with a hard ceiling, and the
timeouts are one second, so no test in this file can hang. Nothing reaches a
network: the client builder is replaced with a function that blocks the way
the real one does.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

import pytest
import requests

from app.agents.runner import analysis_runner
from app.core.config import get_settings
from app.models.errors import (
    ModelNotConfiguredError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from app.models.nemotron import NemotronProvider
from app.models.payload import DocumentPayload
from app.models.provider import AnalysisRequest
from app.schemas.analysis import ErrorCategory
from tests.conftest import upload
from tests.test_workflow import PAGE_TEXT, TRUE_FINDING, single_page_pdf

FAKE_KEY = "nvapi-phase22-fake-key-not-a-credential"

#: Upper bound on any stall in this file. Well above the 1 s timeouts, well
#: below anything that would look like a hung suite.
HOLD = 5.0

VALID_REPLY = json.dumps({"findings": [TRUE_FINDING]})


class Reply:
    def __init__(self, content):
        self.content = content


class ThreadedClient:
    """Behaves like ChatNVIDIA: `ainvoke` runs a blocking call in a thread."""

    def __init__(self, gate: threading.Event | None = None, content: str = VALID_REPLY):
        self.gate = gate
        self.content = content
        self.calls = 0
        self.finished = threading.Event()

    def _generate(self):
        if self.gate is not None:
            self.gate.wait(HOLD)
        self.finished.set()
        return Reply(self.content)

    async def ainvoke(self, messages):
        self.calls += 1
        return await asyncio.get_running_loop().run_in_executor(None, self._generate)


class Builder:
    """Stands in for `_build_client`: blocks like the model-listing request."""

    def __init__(self, gate: threading.Event | None = None, raises: Exception | None = None,
                 client_gate: threading.Event | None = None):
        self.gate = gate
        self.raises = raises
        self.client_gate = client_gate
        self.calls = 0
        self.threads: list[str] = []
        self.returned = threading.Event()
        self.built: list[ThreadedClient] = []

    def __call__(self, provider):
        self.calls += 1
        self.threads.append(threading.current_thread().name)
        if self.gate is not None:
            self.gate.wait(HOLD)
        if self.raises is not None:
            raise self.raises
        client = ThreadedClient(self.client_gate)
        self.built.append(client)
        self.returned.set()
        return client


@pytest.fixture
def fast_timeouts(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    monkeypatch.setenv("MODEL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("QA_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def builder(monkeypatch, fast_timeouts):
    """Install a blocking builder on the real provider; release it on teardown."""
    installed: list[Builder] = []

    def install(**kwargs) -> Builder:
        b = Builder(**kwargs)
        monkeypatch.setattr(NemotronProvider, "_build_client", lambda self: b(self))
        installed.append(b)
        return b

    yield install
    for b in installed:
        for gate in (b.gate, b.client_gate):
            if gate is not None:
                gate.set()


@pytest.fixture
def payload() -> DocumentPayload:
    return DocumentPayload.model_validate({
        "document_id": "doc_p22", "total_pages": 1,
        "pages": [{"page_number": 1, "text": PAGE_TEXT}],
    })


class LoopWatch:
    """Records the longest event-loop stall while running."""

    def __init__(self):
        self.max_stall = 0.0
        self._task = None
        self._stop = False

    async def _run(self):
        last = time.perf_counter()
        while not self._stop:
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            self.max_stall = max(self.max_stall, now - last - 0.02)
            last = now

    async def __aenter__(self):
        self._task = asyncio.create_task(self._run())
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *exc):
        self._stop = True
        await self._task


# ---------------------------------------------------------------------------
# Provider level
# ---------------------------------------------------------------------------


class TestClientConstruction:
    async def test_a_stalled_construction_times_out_without_blocking_the_loop(
        self, builder, payload
    ):
        b = builder(gate=threading.Event())
        provider = NemotronProvider()

        async with LoopWatch() as watch:
            began = time.perf_counter()
            with pytest.raises(ModelTimeoutError):
                await provider.analyze_document(AnalysisRequest(payload=payload))
            elapsed = time.perf_counter() - began

        assert elapsed < 2.0
        assert watch.max_stall < 0.5
        # Built off the loop, in a worker thread.
        assert b.threads and b.threads[0] != threading.main_thread().name

    async def test_a_construction_that_finishes_late_publishes_nothing(
        self, builder, payload
    ):
        """The abandoned build returns a client after the deadline. It must be
        dropped, not stored, and must never be called."""
        gate = threading.Event()
        b = builder(gate=gate)
        provider = NemotronProvider()

        with pytest.raises(ModelTimeoutError):
            await provider.analyze_document(AnalysisRequest(payload=payload))

        gate.set()
        assert await asyncio.to_thread(b.returned.wait, HOLD)
        await asyncio.sleep(0.1)

        assert provider._client is None
        assert b.built[0].calls == 0

        # The next request builds afresh and succeeds.
        result = await provider.analyze_document(AnalysisRequest(payload=payload))
        assert len(result.findings) == 1
        assert b.calls == 2

    async def test_a_construction_network_failure_is_classified_and_logged(
        self, builder, payload, caplog
    ):
        builder(raises=requests.ConnectionError("connection refused"))
        provider = NemotronProvider()

        with caplog.at_level(logging.INFO, logger="app.models.nemotron"):
            with pytest.raises(ModelUnavailableError) as exc:
                await provider.analyze_document(AnalysisRequest(payload=payload))

        assert exc.value.details["reason"] == "network_failure"
        assert any("model call" in r.getMessage() and "network_failure" in r.getMessage()
                   for r in caplog.records)

    async def test_a_stalled_construction_is_logged_as_a_timeout(
        self, builder, payload, caplog
    ):
        builder(gate=threading.Event())
        with caplog.at_level(logging.INFO, logger="app.models.nemotron"):
            with pytest.raises(ModelTimeoutError):
                await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
        assert any("outcome=timeout" in r.getMessage() for r in caplog.records)

    async def test_missing_key_is_still_not_configured_and_starts_no_thread(
        self, builder, payload, monkeypatch
    ):
        b = builder()
        monkeypatch.setenv("NVIDIA_API_KEY", "")
        get_settings.cache_clear()

        with pytest.raises(ModelNotConfiguredError):
            await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
        assert b.calls == 0

    async def test_the_client_is_built_once_per_provider(self, builder, payload):
        b = builder()
        provider = NemotronProvider()
        await provider.analyze_document(AnalysisRequest(payload=payload))
        await provider.analyze_document(AnalysisRequest(payload=payload))
        assert b.calls == 1


class TestModelCall:
    async def test_a_blocking_model_call_times_out_with_a_responsive_loop(
        self, builder, payload
    ):
        builder(client_gate=threading.Event())

        async with LoopWatch() as watch:
            began = time.perf_counter()
            with pytest.raises(ModelTimeoutError):
                await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
            elapsed = time.perf_counter() - began

        assert elapsed < 2.0
        assert watch.max_stall < 0.5

    async def test_construction_and_call_share_one_deadline(self, builder, payload, monkeypatch):
        """0.6 s building + 0.6 s calling exceeds a 1 s budget in total."""

        class SlowClient(ThreadedClient):
            def _generate(self):
                time.sleep(0.6)
                return Reply(self.content)

        def slow_build(self):
            time.sleep(0.6)
            return SlowClient()

        monkeypatch.setattr(NemotronProvider, "_build_client", slow_build)
        began = time.perf_counter()
        with pytest.raises(ModelTimeoutError):
            await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
        assert time.perf_counter() - began < 1.5

    async def test_cancellation_propagates(self, builder, payload):
        builder(client_gate=threading.Event())
        task = asyncio.create_task(
            NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_success_after_a_timeout(self, builder, payload):
        gate = threading.Event()
        builder(client_gate=gate)
        with pytest.raises(ModelTimeoutError):
            await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))

        gate.set()
        result = await NemotronProvider().analyze_document(AnalysisRequest(payload=payload))
        assert len(result.findings) == 1


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_runner():
    analysis_runner.clear()
    yield
    analysis_runner.clear()


@pytest.fixture
def real_provider(monkeypatch, clean_runner):
    """The real NemotronProvider behind both endpoints, a fresh one per call."""
    monkeypatch.setattr("app.agents.runner.get_model_provider", NemotronProvider)
    monkeypatch.setattr("app.api.v1.routes_qa._provider_factory", NemotronProvider)


def _upload(client) -> str:
    return upload(client, single_page_pdf()).json()["document_id"]


def _wait(client, analysis_id: str, limit: float = HOLD + 3) -> dict:
    deadline = time.time() + limit
    body: dict = {}
    while time.time() < deadline:
        body = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.05)
    pytest.fail(f"analysis did not finish; last status {body.get('status')}")


def _health_latency(client) -> float:
    began = time.perf_counter()
    assert client.get("/api/v1/health").status_code == 200
    return time.perf_counter() - began


class TestAnalysisApi:
    def test_a_stalled_construction_is_a_provider_timeout_and_the_server_answers(
        self, client, builder, real_provider
    ):
        gate = threading.Event()
        b = builder(gate=gate)
        document_id = _upload(client)

        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        time.sleep(0.3)  # the build is now stalled in its thread
        assert b.calls == 1
        assert _health_latency(client) < 1.0

        body = _wait(client, analysis_id)
        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.PROVIDER_TIMEOUT
        assert body["verified_count"] is None
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409

    def test_the_abandoned_constructor_cannot_publish_and_the_app_stays_responsive(
        self, client, builder, real_provider
    ):
        """Phase 22 approval requirement: the constructor thread finishes after
        the request timed out. Nothing it returns reaches the job, and the
        application keeps answering throughout."""
        gate = threading.Event()
        b = builder(gate=gate)
        document_id = _upload(client)

        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        failed = _wait(client, analysis_id)
        assert failed["error_category"] == ErrorCategory.PROVIDER_TIMEOUT

        # Let the abandoned build complete with a working client.
        gate.set()
        assert b.returned.wait(HOLD)
        time.sleep(0.3)

        assert _health_latency(client) < 1.0
        after = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        assert after["status"] == "failed"
        assert after["error_category"] == ErrorCategory.PROVIDER_TIMEOUT
        assert after["verified_count"] is None
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409
        # The client it built was never asked anything.
        assert b.built[0].calls == 0

        # The user asks again: a new analysis, a new build, a real result.
        retry = client.post(f"/api/v1/documents/{document_id}/analyze").json()
        assert retry["reused"] is False
        done = _wait(client, retry["analysis_id"])
        assert done["status"] == "completed"
        assert b.calls == 2

    def test_a_model_call_that_completes_late_is_discarded(
        self, client, builder, real_provider
    ):
        gate = threading.Event()
        b = builder(client_gate=gate)
        document_id = _upload(client)

        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        assert _wait(client, analysis_id)["error_category"] == ErrorCategory.PROVIDER_TIMEOUT

        gate.set()
        assert b.built[0].finished.wait(HOLD)
        time.sleep(0.3)

        after = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        assert after["status"] == "failed"
        assert after["verified_count"] is None
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409

    def test_concurrent_stalled_analyses_both_fail_cleanly_and_can_rerun(
        self, client, builder, real_provider
    ):
        gate = threading.Event()
        builder(client_gate=gate)
        documents = [_upload(client), _upload(client)]

        ids = [client.post(f"/api/v1/documents/{d}/analyze").json()["analysis_id"]
               for d in documents]
        for analysis_id in ids:
            body = _wait(client, analysis_id)
            assert body["error_category"] == ErrorCategory.PROVIDER_TIMEOUT

        gate.set()
        for d in documents:
            retry = client.post(f"/api/v1/documents/{d}/analyze").json()
            assert _wait(client, retry["analysis_id"])["status"] == "completed"

    def test_timeout_logs_carry_no_key_and_no_document_text(
        self, client, builder, real_provider, caplog
    ):
        builder(gate=threading.Event())
        document_id = _upload(client)

        with caplog.at_level(logging.DEBUG):
            analysis_id = client.post(
                f"/api/v1/documents/{document_id}/analyze"
            ).json()["analysis_id"]
            _wait(client, analysis_id)

        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "outcome=timeout" in text
        assert FAKE_KEY not in text
        assert "written notice" not in text
        assert "terminate this agreement" not in text


class TestAskApi:
    def test_a_stalled_construction_is_a_504_within_the_question_budget(
        self, client, builder, real_provider
    ):
        builder(gate=threading.Event())
        document_id = _upload(client)
        client.post(f"/api/v1/documents/{document_id}/extract")

        began = time.perf_counter()
        response = client.post(
            f"/api/v1/documents/{document_id}/ask", json={"question": "When can it end?"}
        )
        elapsed = time.perf_counter() - began

        assert response.status_code == 504
        assert response.json()["error"]["code"] == "model_timeout"
        assert elapsed < 2.5
        assert FAKE_KEY not in response.text
        assert _health_latency(client) < 1.0
