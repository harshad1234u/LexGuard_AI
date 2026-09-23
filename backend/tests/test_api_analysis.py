"""Phase 7: the asynchronous analysis API.

The HTTP request never waits for the model. These tests drive the real
endpoints with a fake provider behind them and poll like a client would.
"""

from __future__ import annotations

import time

import pytest

from app.agents.runner import analysis_runner
from app.models.errors import ModelUnavailableError, make_error
from app.schemas.analysis import ErrorCategory
from tests.conftest import make_pdf, make_pdf_with_image_only_page, upload
from tests.test_workflow import TRUE_FINDING, FakeProvider, finding, single_page_pdf


@pytest.fixture(autouse=True)
def clean_runner():
    analysis_runner.clear()
    yield
    analysis_runner.clear()


@pytest.fixture
def use_provider(monkeypatch):
    """Put a fake provider behind the real endpoints."""

    def install(provider: FakeProvider) -> FakeProvider:
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: provider)
        return provider

    return install


def wait_for_terminal(client, analysis_id: str, timeout: float = 10.0) -> dict:
    """Poll status the way a client would, until the analysis settles."""
    deadline = time.time() + timeout
    body = {}
    while time.time() < deadline:
        body = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.05)
    pytest.fail(f"analysis did not finish; last status {body.get('status')}")


def start(client, document_id: str):
    return client.post(f"/api/v1/documents/{document_id}/analyze")


def upload_pdf(client, content: bytes) -> str:
    return upload(client, content).json()["document_id"]


class TestStartAnalysis:
    def test_analyze_returns_202_with_an_analysis_id(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())

        response = start(client, document_id)

        assert response.status_code == 202
        body = response.json()
        assert body["analysis_id"].startswith("an_")
        assert body["document_id"] == document_id
        assert body["status"] in {"queued", "running", "completed"}
        assert body["reused"] is False

    def test_http_request_returns_before_the_model_finishes(self, client, use_provider):
        """The request must not be tied to the model's duration."""
        use_provider(FakeProvider(delay=0.6))
        document_id = upload_pdf(client, single_page_pdf())

        began = time.perf_counter()
        response = start(client, document_id)
        elapsed = time.perf_counter() - began

        assert response.status_code == 202
        assert elapsed < 0.5, "the analyze request waited for the model"

    def test_unknown_document_is_404(self, client, use_provider):
        use_provider(FakeProvider())
        assert start(client, "doc_missing").status_code == 404


class TestPollingToCompletion:
    def test_status_progresses_to_completed(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "completed"
        assert body["stage"] == "done"
        assert body["verified_count"] == 1
        assert body["withheld_count"] == 0
        assert body["completed_at"] is not None
        assert body["duration_ms"] >= 0

    def test_status_exposes_the_coverage_it_acted_on(self, client, use_provider):
        use_provider(FakeProvider(findings=[]))
        document_id = upload_pdf(client, make_pdf(pages=3))
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)
        assert body["coverage"]["expected_pages"] == 3
        assert body["coverage"]["processed_pages"] == 3

    def test_unknown_analysis_is_404(self, client):
        assert client.get("/api/v1/analysis/an_missing/status").status_code == 404

    def test_stage_reports_the_model_call_while_it_is_running(self, client, use_provider):
        """The stage a client polls must name what is actually happening.

        The model call is the long one, so it is the stage that matters: a
        client showing "preparing the document" for 37 seconds is reporting
        the previous step, not the current one.
        """
        use_provider(FakeProvider(delay=1.0))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        seen = []
        deadline = time.time() + 5.0
        while time.time() < deadline:
            body = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
            if not seen or seen[-1] != body["stage"]:
                seen.append(body["stage"])
            if body["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert "analyzing" in seen, f"the model stage was never reported; saw {seen}"
        assert seen[-1] == "done"
        # Stages are reported in the workflow's order, never out of sequence.
        order = [
            "queued", "validating", "ingesting", "checking_coverage",
            "building_document_map", "analyzing", "verifying", "gating_output", "done",
        ]
        assert seen == sorted(seen, key=order.index)

    def test_a_blocked_analysis_never_reports_the_model_stage(self, client, use_provider):
        """A document that fails coverage stops before the model.

        The stage it settles on must say so, rather than implying an analysis
        that never happened.
        """
        provider = use_provider(FakeProvider())
        document_id = upload_pdf(client, make_pdf_with_image_only_page(3, image_page=2))
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["stage"] == "checking_coverage"
        assert provider.calls == []


class TestFindingsEndpoint:
    def test_findings_available_after_completion(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        body = client.get(f"/api/v1/documents/{document_id}/findings").json()

        assert body["status"] == "completed"
        assert len(body["result"]["findings"]) == 1
        assert body["result"]["findings"][0]["verification_status"] == "verified"
        assert body["result"]["findings"][0]["evidence"]["page"] == 1

    def test_findings_before_any_analysis_is_404(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 404

    def test_findings_while_running_is_409(self, client, use_provider):
        use_provider(FakeProvider(delay=1.0))
        document_id = upload_pdf(client, single_page_pdf())
        start(client, document_id)

        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409

    def test_withheld_findings_are_counted_not_returned(self, client, use_provider):
        use_provider(
            FakeProvider(
                findings=[
                    TRUE_FINDING,
                    finding(claim="Either party may terminate with 60 days' notice."),
                ]
            )
        )
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        response = client.get(f"/api/v1/documents/{document_id}/findings")
        body = response.json()

        assert len(body["result"]["findings"]) == 1
        assert body["result"]["withheld"]["total"] == 1
        assert body["result"]["withheld"]["rejected"] == 1
        assert "60 days" not in response.text


class TestIdempotency:
    def test_repeated_analyze_while_running_reuses_the_analysis(self, client, use_provider):
        """A double-clicked button must not buy two inferences."""
        provider = use_provider(FakeProvider(delay=0.5))
        document_id = upload_pdf(client, single_page_pdf())

        first = start(client, document_id).json()
        second = start(client, document_id).json()
        third = start(client, document_id).json()

        assert first["analysis_id"] == second["analysis_id"] == third["analysis_id"]
        assert second["reused"] is True and third["reused"] is True

        wait_for_terminal(client, first["analysis_id"])
        assert len(provider.calls) == 1, "the model was called more than once"

    def test_analyze_after_completion_returns_the_existing_result(self, client, use_provider):
        provider = use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        first = start(client, document_id).json()
        wait_for_terminal(client, first["analysis_id"])

        again = start(client, document_id)

        assert again.status_code == 200
        assert again.json()["analysis_id"] == first["analysis_id"]
        assert again.json()["reused"] is True
        assert len(provider.calls) == 1

    def test_analyze_after_failure_starts_a_new_analysis(self, client, use_provider, monkeypatch):
        """A failure is retryable - but only because the user asked again."""
        failing = use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        first = start(client, document_id).json()
        wait_for_terminal(client, first["analysis_id"])

        working = use_provider(FakeProvider())
        second = start(client, document_id).json()

        assert second["analysis_id"] != first["analysis_id"]
        assert second["reused"] is False
        wait_for_terminal(client, second["analysis_id"])
        assert len(failing.calls) == 1 and len(working.calls) == 1

    def test_discarding_a_document_discards_its_analysis(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert client.get(f"/api/v1/analysis/{analysis_id}/status").status_code == 404


class TestTerminalFailures:
    def test_provider_failure_is_a_terminal_failed_analysis(self, client, use_provider):
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.PROVIDER_UNAVAILABLE
        assert body["stage"] != "done"
        assert body["verified_count"] is None

    def test_workflow_timeout_is_a_terminal_failure(self, client, use_provider, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("ANALYSIS_TIMEOUT_SECONDS", "0")
        get_settings.cache_clear()

        use_provider(FakeProvider(delay=2.0))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.ANALYSIS_TIMEOUT

    def test_malformed_model_output_is_a_terminal_failure(self, client, use_provider):
        use_provider(FakeProvider(raw="not json"))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)
        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.MODEL_OUTPUT_INVALID

    def test_coverage_failure_is_a_terminal_failure_with_no_model_call(
        self, client, use_provider
    ):
        provider = use_provider(FakeProvider())
        content = make_pdf(pages=6)
        document_id = upload_pdf(client, content[: len(content) // 3])
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.COVERAGE_ERROR
        assert provider.calls == []
        assert "repaired" in body["error_message"].lower()

    def test_scanned_page_blocks_analysis_at_the_api(self, client, use_provider):
        provider = use_provider(FakeProvider())
        document_id = upload_pdf(client, make_pdf_with_image_only_page(total=3, image_page=2))
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["error_category"] == ErrorCategory.COVERAGE_ERROR
        assert provider.calls == []

    def test_failed_analysis_never_reports_completed(self, client, use_provider):
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)
        assert body["status"] != "completed"
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409


class TestResponseSafety:
    def test_status_response_exposes_no_secrets(self, client, use_provider, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-canary-must-not-leak-1234567890")
        from app.core.config import get_settings

        get_settings.cache_clear()

        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/status")
        assert "nvapi" not in response.text
        assert "canary" not in response.text

    def test_status_response_carries_no_document_text(self, client, use_provider):
        secret = "Confidential indemnity provision"
        use_provider(FakeProvider(findings=[]))
        document_id = upload_pdf(client, single_page_pdf(f"1. Terms. {secret}."))
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/status")
        assert "indemnity" not in response.text.lower()

    def test_findings_response_carries_only_evidence_quotes(self, client, use_provider):
        """Verified evidence is shown; the rest of the page is not."""
        unrelated = "The Supplier operates from Building 7 in the Industrial Estate"
        use_provider(FakeProvider())
        document_id = upload_pdf(client, single_page_pdf(f"{PAGE_EXTRA}{unrelated}."))
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        response = client.get(f"/api/v1/documents/{document_id}/findings")
        assert "30 days' written notice" in response.text
        assert "Industrial Estate" not in response.text

    def test_provider_exception_text_never_reaches_the_client(self, client, use_provider):
        use_provider(FakeProvider(raises=RuntimeError("internal detail: host db-3 refused")))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)
        assert "db-3" not in str(body)
        assert "Traceback" not in str(body)

    def test_a_crash_in_the_workflow_leaks_nothing(self, client, use_provider, monkeypatch,
                                                   caplog):
        """The runner's last-resort catch is a leak risk, so it is tested.

        An exception escaping the graph machinery carries whatever it was
        handed - here, document text. Neither the log nor the response may
        repeat it, and the analysis must still settle as a clean failure
        rather than hanging in `running`.
        """
        secret = "Confidential indemnity provision"
        use_provider(FakeProvider())

        def crash(*_args, **_kwargs):
            raise RuntimeError(f"state rejected: {secret}")

        monkeypatch.setattr("app.agents.runner.build_graph", crash)
        document_id = upload_pdf(client, single_page_pdf(f"1. Terms. {secret}."))

        with caplog.at_level("DEBUG"):
            analysis_id = start(client, document_id).json()["analysis_id"]
            body = wait_for_terminal(client, analysis_id)

        assert body["status"] == "failed"
        assert body["error_category"] == "internal_error"
        assert "indemnity" not in str(body).lower()
        assert "indemnity" not in caplog.text.lower()
        assert "Traceback" not in caplog.text


PAGE_EXTRA = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
)


class TestAnalysisStoppedContract:
    """What a client may conclude when the model step fails.

    The Phase 18B screenshot showed `Analysis stopped / Verification waiting /
    Results not available`. That reading is only trustworthy if the backend
    cannot produce any other combination after a provider failure, so the
    combination itself is pinned here rather than inferred from the UI.
    """

    def test_a_provider_failure_leaves_verification_unrun_and_results_absent(
        self, client, use_provider
    ):
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)

        # Stopped inside the model step, and never past it.
        assert body["status"] == "failed"
        assert body["stage"] == "analyzing"
        assert body["error_category"] == ErrorCategory.PROVIDER_UNAVAILABLE

        # Verification never ran, so it has nothing to report. These being
        # None - not 0 - is the distinction between "checked, found nothing"
        # and "never checked".
        assert body["proposed_count"] is None
        assert body["verified_count"] is None
        assert body["withheld_count"] is None

        # The document's own coverage is still reported, because it succeeded.
        assert body["coverage"]["status"] == "complete"

    def test_no_findings_are_retrievable_after_a_provider_failure(self, client, use_provider):
        """A failed analysis must not leave a result behind to fetch."""
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        wait_for_terminal(client, start(client, document_id).json()["analysis_id"])

        response = client.get(f"/api/v1/documents/{document_id}/findings")
        assert response.status_code == 409
        assert "findings" not in response.text

    def test_a_provider_failure_releases_no_model_text(self, client, use_provider):
        """Nothing the model said - or that the provider said - reaches the client."""
        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]

        body = wait_for_terminal(client, analysis_id)
        text = client.get(f"/api/v1/analysis/{analysis_id}/status").text

        assert body["error_message"] == "The analysis service is temporarily unavailable."
        for leak in ("Traceback", "nvapi", "ResourceExhausted", "provider_capacity"):
            assert leak not in text, f"leaked: {leak}"


class TestManualRetryOnly:
    """Retrying is the user's decision, and stays that way.

    docs/03_AI_AGENT_SPEC.md sec. 8 forbids an automatic retry: a silent loop
    turns one rate-limit into several on a metered API. These tests exist so
    that stays true by measurement rather than by intention.
    """

    def test_a_failure_buys_exactly_one_provider_call(self, client, use_provider):
        provider = use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        wait_for_terminal(client, start(client, document_id).json()["analysis_id"])

        assert len(provider.calls) == 1, "the provider was called more than once"

    def test_two_failures_are_two_attempts_and_no_more(self, client, use_provider):
        """Failure, manual retry, failure again. No automatic third attempt."""
        provider = use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())

        first = start(client, document_id).json()
        wait_for_terminal(client, first["analysis_id"])
        second = start(client, document_id).json()
        second_body = wait_for_terminal(client, second["analysis_id"])

        assert second["analysis_id"] != first["analysis_id"]
        assert second["reused"] is False
        assert second_body["status"] == "failed"
        assert len(provider.calls) == 2, "an attempt happened that nobody asked for"

    def test_a_retry_after_failure_succeeds_and_leaves_no_trace_of_the_failure(
        self, client, use_provider
    ):
        """The flow the user is actually waiting for: failure, then success."""
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        failed = wait_for_terminal(client, start(client, document_id).json()["analysis_id"])
        assert failed["status"] == "failed"

        working = use_provider(FakeProvider())
        retried = start(client, document_id).json()
        body = wait_for_terminal(client, retried["analysis_id"])

        # A clean success, carrying none of the previous attempt's state.
        assert body["status"] == "completed"
        assert body["error_category"] is None
        assert body["error_message"] is None
        assert body["verified_count"] is not None
        assert len(working.calls) == 1

        # And the findings are now genuinely retrievable.
        findings = client.get(f"/api/v1/documents/{document_id}/findings")
        assert findings.status_code == 200
        assert findings.json()["analysis_id"] == retried["analysis_id"]

    def test_the_failed_attempt_is_not_also_reported_as_a_result(self, client, use_provider):
        """Two attempts, one result - the successful one."""
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        first = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, first)

        use_provider(FakeProvider())
        second = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, second)

        latest = client.get(f"/api/v1/documents/{document_id}/findings").json()
        assert latest["analysis_id"] == second
        # The failed attempt is still its own record, still failed.
        assert client.get(f"/api/v1/analysis/{first}/status").json()["status"] == "failed"


class TestProviderReasonIsRecorded:
    """An analysis failure has to be identifiable after the fact.

    `error_category` is coarse: four distinct provider failures share
    `provider_unavailable`. The provider's own `reason` is what separates a
    capacity limit from a network fault from an exception nobody has seen, and
    without it in the analysis log a failure is recorded but not diagnosable -
    which is precisely why the screenshot's cause could not be established.
    """

    def test_the_reason_reaches_the_analysis_log(self, client, use_provider, caplog):
        import logging

        caplog.set_level(logging.INFO, logger="app.agents.nodes")
        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        document_id = upload_pdf(client, single_page_pdf())
        wait_for_terminal(client, start(client, document_id).json()["analysis_id"])

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "model_failed" in logged
        assert "category=provider_unavailable" in logged
        assert "reason=provider_capacity" in logged

    def test_a_reasonless_error_is_logged_as_unspecified_not_omitted(
        self, client, use_provider, caplog
    ):
        import logging

        caplog.set_level(logging.INFO, logger="app.agents.nodes")
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload_pdf(client, single_page_pdf())
        wait_for_terminal(client, start(client, document_id).json()["analysis_id"])

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "reason=unspecified" in logged

    def test_the_reason_is_not_sent_to_the_client(self, client, use_provider):
        """Operators get the diagnosis; the analysis status response does not."""
        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        document_id = upload_pdf(client, single_page_pdf())
        analysis_id = start(client, document_id).json()["analysis_id"]
        wait_for_terminal(client, analysis_id)

        body = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        assert "reason" not in body
        assert set(body) >= {"status", "stage", "error_category", "error_message"}
