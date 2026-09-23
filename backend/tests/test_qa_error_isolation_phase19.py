"""Phase 19: what a failed question says, and what it must leave alone.

A provider outage during `/ask` reached the browser carrying the sentence
"The analysis service is temporarily unavailable." It was accurate about the
provider and wrong about the feature: the analysis on the same screen had
completed, and the user was told it had not. The classification was never at
fault - `SAFE_MESSAGES` is simply written for the analysis, and both paths
call the same provider through the same abstraction.

So this module pins two separate things:

    the sentence a question failure carries
    the fact that nothing about a finished analysis moves when one happens

The fake provider stands in for Nemotron; the coverage gate, the verifier, the
output gate and the real analysis workflow all run. No test here reaches NVIDIA.
"""

from __future__ import annotations

import logging
import time

import pytest

from app.models.errors import (
    ModelNotConfiguredError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelUnavailableError,
    make_error,
)
from tests.test_api_qa import FakeProvider, ask, upload_and_extract, use_provider  # noqa: F401

#: Words that name the other feature. None may appear in a question failure.
ANALYSIS_WORDS = ("analysis service", "Document analysis", "The analysis")


def completed_analysis(client, monkeypatch, document_id: str) -> dict:
    """Drive a real analysis to `completed` and return its status body.

    The analysis and Q&A providers are injected at different seams - the
    runner resolves its own - so a test can fail one while the other succeeds,
    which is the whole situation under examination here.
    """
    from tests.test_workflow import FakeProvider as AnalysisProvider

    monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: AnalysisProvider())
    started = client.post(f"/api/v1/documents/{document_id}/analyze")
    assert started.status_code in {200, 202}
    analysis_id = started.json()["analysis_id"]

    deadline = time.time() + 10.0
    while time.time() < deadline:
        body = client.get(f"/api/v1/analysis/{analysis_id}/status").json()
        if body["status"] in {"completed", "failed"}:
            assert body["status"] == "completed", body.get("error_message")
            return body
        time.sleep(0.05)
    pytest.fail("the analysis never reached a terminal state")


class TestTheSentenceAQuestionFailureCarries:
    @pytest.mark.parametrize(
        "error,status",
        [
            (make_error(ModelUnavailableError), 503),
            (make_error(ModelTimeoutError), 504),
            (make_error(ModelRateLimitError), 429),
            (make_error(ModelNotConfiguredError), 503),
        ],
    )
    def test_a_provider_failure_never_names_the_analysis(
        self, client, use_provider, error, status
    ):
        use_provider(FakeProvider(raises=error))
        document_id = upload_and_extract(client)

        response = ask(client, document_id)

        assert response.status_code == status
        message = response.json()["error"]["message"]
        assert message
        for word in ANALYSIS_WORDS:
            assert word not in message, f"a question failure said {word!r}: {message!r}"

    def test_the_capacity_outage_from_the_real_run_names_the_question(
        self, client, use_provider
    ):
        """The exact failure the Phase 19 screenshot was taken during."""
        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        document_id = upload_and_extract(client)

        response = ask(client, document_id)

        assert response.status_code == 503
        message = response.json()["error"]["message"]
        assert "question" in message.lower()
        assert "analysis service" not in message
        # It says what did not happen, so silence is not read as an answer.
        assert "No answer" in message

    def test_the_route_level_timeout_is_worded_as_a_question_failure(
        self, client, use_provider, monkeypatch
    ):
        """The `/ask` budget firing, rather than an error the provider raised."""
        from app.core.config import get_settings

        monkeypatch.setenv("QA_TIMEOUT_SECONDS", "1")
        get_settings.cache_clear()

        use_provider(FakeProvider(delay=10.0))
        document_id = upload_and_extract(client)

        response = ask(client, document_id)

        assert response.status_code == 504
        body = response.json()
        message = body["error"]["message"]
        assert "question" in message.lower()
        assert "analysis" not in message.lower()
        # A failure never arrives carrying an answer shape.
        assert "answer" not in body
        assert "status" not in body

    def test_an_unexpected_exception_is_worded_as_a_question_failure(
        self, client, use_provider
    ):
        use_provider(FakeProvider(raises=RuntimeError("host db-3 refused connection")))
        document_id = upload_and_extract(client)

        response = ask(client, document_id)

        assert response.status_code == 503
        assert "analysis service" not in response.json()["error"]["message"]
        assert "db-3" not in response.text

    def test_only_the_wording_changes(self, client, use_provider):
        """Re-wording must not become re-grading.

        A client switches on `code` and `status`; both are the provider's
        verdict and neither is this route's to revise. The `reason` detail is
        what makes a failure diagnosable afterwards, so it is carried over too.
        """
        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        document_id = upload_and_extract(client)

        response = ask(client, document_id)

        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "model_unavailable"
        assert error["details"]["reason"] == "provider_capacity"

    def test_the_analysis_path_keeps_its_own_wording(self):
        """The analysis message is not collateral damage of the Q&A fix."""
        from app.models.errors import SAFE_MESSAGES

        assert (
            SAFE_MESSAGES[ModelUnavailableError]
            == "The analysis service is temporarily unavailable."
        )

    def test_every_provider_failure_has_a_question_wording(self):
        """A new error class must not silently fall back to analysis wording."""
        from app.models.errors import QUESTION_SAFE_MESSAGES, SAFE_MESSAGES

        assert set(QUESTION_SAFE_MESSAGES) == set(SAFE_MESSAGES)
        for kind, message in QUESTION_SAFE_MESSAGES.items():
            assert message.strip()
            assert "analysis service" not in message
            assert message != SAFE_MESSAGES[kind]


class TestAQuestionFailureLeavesTheAnalysisAlone:
    def test_a_completed_analysis_is_unchanged_by_a_failed_question(
        self, client, use_provider, monkeypatch
    ):
        """The state in the screenshot: results on screen, then a 503 question.

        Asserted against the endpoints the frontend actually reads, because
        "the analysis still shows" is a claim about what those return - not
        about a variable held somewhere inside the backend.
        """
        document_id = upload_and_extract(client)
        before_status = completed_analysis(client, monkeypatch, document_id)
        before_findings = client.get(f"/api/v1/documents/{document_id}/findings").json()
        before_values = client.get(f"/api/v1/documents/{document_id}/values").json()

        use_provider(
            FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        )
        assert ask(client, document_id).status_code == 503

        after_status = client.get(
            f"/api/v1/analysis/{before_status['analysis_id']}/status"
        ).json()
        assert after_status == before_status
        assert after_status["status"] == "completed"
        assert after_status["error_category"] is None
        assert after_status["error_message"] is None

        assert client.get(f"/api/v1/documents/{document_id}/findings").json() == (
            before_findings
        )
        assert client.get(f"/api/v1/documents/{document_id}/values").json() == before_values

    def test_a_failed_question_starts_no_analysis(self, client, use_provider, monkeypatch):
        """Retrying a question is `/ask` and nothing else."""
        from app.agents.runner import analysis_runner

        document_id = upload_and_extract(client)
        completed_analysis(client, monkeypatch, document_id)
        before = analysis_runner.for_document(document_id).analysis_id

        provider = use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        assert ask(client, document_id).status_code == 503
        assert ask(client, document_id).status_code == 503

        # Two questions asked, two model calls, and the same analysis as before.
        assert len(provider.calls) == 2
        assert analysis_runner.for_document(document_id).analysis_id == before

    def test_a_question_that_fails_then_succeeds_leaves_the_analysis_alone(
        self, client, use_provider, monkeypatch
    ):
        document_id = upload_and_extract(client)
        before = completed_analysis(client, monkeypatch, document_id)

        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        assert ask(client, document_id).status_code == 503

        use_provider(FakeProvider())
        recovered = ask(client, document_id)
        assert recovered.status_code == 200
        assert recovered.json()["status"] in {"supported", "partially_supported", "not_found"}

        assert client.get(f"/api/v1/analysis/{before['analysis_id']}/status").json() == before

    def test_a_question_that_finds_nothing_is_not_an_outage(self, client, use_provider):
        """`not_found` stays a 200, beside a completed analysis or without one.

        The two states are one HTTP status apart and look alike from outside,
        and only one of them means the service failed.
        """
        use_provider(FakeProvider(raw='{"answer": "", "evidence": []}'))
        document_id = upload_and_extract(client)

        response = ask(client, document_id, question="What is the governing law?")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "not_found"
        assert "error" not in body


class TestAFailedQuestionLeaksNothing:
    def test_neither_the_response_nor_the_log_carries_anything_sensitive(
        self, client, use_provider, monkeypatch, caplog
    ):
        """The secret, the question, the document text, and the upstream
        exception's own words are all absent from both surfaces."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-canary-must-not-leak-9876543210")
        use_provider(
            FakeProvider(
                raises=RuntimeError(
                    "Authorization: Bearer nvapi-canary-must-not-leak-9876543210"
                )
            )
        )
        document_id = upload_and_extract(client)

        with caplog.at_level(logging.DEBUG):
            response = ask(
                client,
                document_id,
                question="What does the termination clause say about GBP 5,000?",
            )

        assert response.status_code == 503
        logged = "\n".join(record.getMessage() for record in caplog.records)
        for surface in (response.text, logged):
            assert "nvapi-canary" not in surface
            assert "Authorization" not in surface
            assert "Bearer" not in surface
            assert "SERVICES AGREEMENT" not in surface
            assert "GBP 5,000" not in surface
            assert "Traceback" not in surface

        # The bounded metadata these logs exist to carry is still there.
        assert "qa asked" in logged
        assert f"document_id={document_id}" in logged
        assert "question_chars=" in logged
