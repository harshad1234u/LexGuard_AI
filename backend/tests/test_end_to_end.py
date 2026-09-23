"""Phase 8: the complete MVP journey, driven through the public API only.

Every other test file checks one layer. This one checks that the layers
compose - that a client holding nothing but a PDF and the published contract
can get from a file to evidence-grounded findings, and that the paths which
should stop it actually do.

    upload -> status -> extract -> status -> analyze -> poll -> findings

The model is faked; everything else is real, including the coverage gate, the
Phase 5 verifier and the output gate. No test here reaches NVIDIA.
"""

from __future__ import annotations

import time

import pytest

from app.agents.runner import analysis_runner
from app.models.errors import ModelUnavailableError, make_error
from tests.conftest import (
    make_pdf,
    make_pdf_with_blank_pages,
    make_pdf_with_image_only_page,
    upload,
)
from tests.test_workflow import FakeProvider, finding

CONTRACT_TEXT = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
)


@pytest.fixture(autouse=True)
def clean_runner():
    analysis_runner.clear()
    yield
    analysis_runner.clear()


@pytest.fixture
def use_provider(monkeypatch):
    def install(provider: FakeProvider) -> FakeProvider:
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: provider)
        return provider

    return install


def contract_pdf(text: str = CONTRACT_TEXT) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def poll_until_terminal(client, analysis_id: str, timeout: float = 10.0) -> dict:
    """Poll exactly as the frontend does, and stop at a terminal status."""
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/v1/analysis/{analysis_id}/status")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.05)
    pytest.fail(f"analysis never settled; last status {body.get('status')!r}")


class TestHappyPath:
    """The journey the product exists to deliver."""

    def test_a_client_gets_from_a_pdf_to_grounded_findings(self, client, use_provider):
        provider = use_provider(FakeProvider())

        # 1. Upload.
        uploaded = upload(client, contract_pdf())
        assert uploaded.status_code == 201
        document_id = uploaded.json()["document_id"]
        assert uploaded.json()["page_count"] == 1
        assert uploaded.json()["source_repaired"] is False

        # 2. Status before extraction: not yet eligible, and honest about why.
        before = client.get(f"/api/v1/documents/{document_id}/status").json()
        assert before["coverage_status"] == "pending"
        assert before["analysis_eligible"] is False
        assert before["processed_pages"] == 0

        # 3. Extract.
        extracted = client.post(f"/api/v1/documents/{document_id}/extract")
        assert extracted.status_code == 200
        assert extracted.json()["coverage"]["status"] == "complete"

        # 4. Status after extraction: eligible, with the counts that earned it.
        after = client.get(f"/api/v1/documents/{document_id}/status").json()
        assert after["coverage_status"] == "complete"
        assert after["analysis_eligible"] is True
        assert after["processed_pages"] == after["expected_pages"] == 1
        assert after["failed_pages"] == [] and after["unreadable_pages"] == []

        # 5. Start the analysis. The request does not wait for the model.
        started = client.post(f"/api/v1/documents/{document_id}/analyze")
        assert started.status_code == 202
        analysis_id = started.json()["analysis_id"]
        assert started.json()["reused"] is False

        # 6. Poll to completion.
        final = poll_until_terminal(client, analysis_id)
        assert final["status"] == "completed"
        assert final["stage"] == "done"
        assert final["coverage"]["processed_pages"] == 1

        # 7. Retrieve the gated findings.
        findings = client.get(f"/api/v1/documents/{document_id}/findings")
        assert findings.status_code == 200
        result = findings.json()["result"]

        # 8. What came back is grounded: verified, quoted, and page-numbered.
        assert len(result["findings"]) == 1
        item = result["findings"][0]
        assert item["verification_status"] == "verified"
        assert item["evidence"]["quote"] == "30 days' written notice"
        assert item["evidence"]["page"] == 1
        assert result["insufficient_evidence"] is False
        assert provider.calls and len(provider.calls) == 1

    def test_the_journey_needs_no_undocumented_endpoint(self, client, use_provider):
        """Every call the frontend makes is one the API spec publishes."""
        use_provider(FakeProvider())
        document_id = upload(client, contract_pdf()).json()["document_id"]

        client.post(f"/api/v1/documents/{document_id}/extract")
        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        poll_until_terminal(client, analysis_id)

        for path in [
            "/api/v1/health",
            f"/api/v1/documents/{document_id}/status",
            f"/api/v1/documents/{document_id}/manifest",
            f"/api/v1/analysis/{analysis_id}/status",
            f"/api/v1/documents/{document_id}/findings",
        ]:
            assert client.get(path).status_code == 200, path


class TestBlockedJourneys:
    """Paths that must stop, and stop before the model is paid for."""

    def test_a_scanned_page_stops_the_journey_at_coverage(self, client, use_provider):
        provider = use_provider(FakeProvider())
        document_id = upload(
            client, make_pdf_with_image_only_page(3, image_page=2)
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")

        status = client.get(f"/api/v1/documents/{document_id}/status").json()
        assert status["analysis_eligible"] is False
        assert status["unreadable_pages"] == [2]

        # The backend enforces this independently of any frontend check.
        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        final = poll_until_terminal(client, analysis_id)

        assert final["status"] == "failed"
        assert final["error_category"] == "coverage_error"
        assert provider.calls == [], "the model was invoked for an ineligible document"
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409

    def test_a_genuinely_blank_page_does_not_stop_the_journey(self, client, use_provider):
        """Blank is not the same as unread, and the gate must tell them apart.

        A blank page held no content to miss, so it counts as processed. A
        scanned page held content the application failed to capture, so it
        does not. Conflating the two would either block ordinary documents or
        wave through ones that were never fully read.
        """
        provider = use_provider(FakeProvider(findings=[]))
        document_id = upload(
            client, make_pdf_with_blank_pages(3, blank={2})
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")

        status = client.get(f"/api/v1/documents/{document_id}/status").json()
        assert status["coverage_status"] == "complete"
        assert status["analysis_eligible"] is True
        assert status["unreadable_pages"] == []

        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        assert poll_until_terminal(client, analysis_id)["status"] == "completed"
        assert len(provider.calls) == 1

    def test_analysis_without_extraction_is_refused_not_guessed(self, client, use_provider):
        """Skipping the extract step must fail the gate, not silently extract.

        The workflow ingests on demand, so this document does get read - but
        the verdict still comes from the coverage controller, and an
        ineligible document never reaches the provider.
        """
        provider = use_provider(FakeProvider())
        document_id = upload(
            client, make_pdf_with_image_only_page(2, image_page=1)
        ).json()["document_id"]

        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        final = poll_until_terminal(client, analysis_id)

        assert final["status"] == "failed"
        assert final["error_category"] == "coverage_error"
        assert provider.calls == []

    def test_an_oversized_upload_never_becomes_a_document(self, client):
        oversized = b"%PDF-1.4\n" + b"0" * (3 * 1024 * 1024)
        response = upload(client, oversized)

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"


class TestFailureIsVisibleAndSafe:
    def test_a_provider_failure_ends_the_journey_readably(self, client, use_provider):
        use_provider(FakeProvider(raises=make_error(ModelUnavailableError)))
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")

        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        final = poll_until_terminal(client, analysis_id)

        assert final["status"] == "failed"
        assert final["error_category"] == "provider_unavailable"
        # Readable by a non-technical user, and free of internals.
        assert final["error_message"]
        assert "Traceback" not in final["error_message"]
        assert "nvapi" not in str(final)
        # And no findings are reachable.
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 409

    def test_a_document_whose_findings_all_fail_verification_says_so(
        self, client, use_provider
    ):
        """The model proposed; nothing survived. That is a distinct state.

        Not "no risks found" - the document was simply never confirmed to
        support anything the model said.
        """
        use_provider(
            FakeProvider(
                findings=[
                    finding(claim="Either party may terminate with 60 days' notice."),
                    finding(evidence={"page": 99}),
                ]
            )
        )
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")

        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        assert poll_until_terminal(client, analysis_id)["status"] == "completed"

        result = client.get(f"/api/v1/documents/{document_id}/findings").json()["result"]
        assert result["findings"] == []
        assert result["insufficient_evidence"] is True
        assert result["withheld"]["total"] == 2
        # The rejected text itself never reaches the client.
        assert "60 days" not in str(result)

    def test_discarding_a_document_ends_the_journey_everywhere(self, client, use_provider):
        use_provider(FakeProvider())
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")
        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]
        poll_until_terminal(client, analysis_id)

        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204

        assert client.get(f"/api/v1/documents/{document_id}/status").status_code == 404
        assert client.get(f"/api/v1/analysis/{analysis_id}/status").status_code == 404
        assert client.get(f"/api/v1/documents/{document_id}/findings").status_code == 404


class TestRepeatedJourneys:
    def test_a_second_analyze_never_buys_a_second_inference(self, client, use_provider):
        """What a double-clicked button must cost: one call."""
        provider = use_provider(FakeProvider(delay=0.4))
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")

        first = client.post(f"/api/v1/documents/{document_id}/analyze").json()
        again = client.post(f"/api/v1/documents/{document_id}/analyze").json()
        assert again["analysis_id"] == first["analysis_id"]
        assert again["reused"] is True

        poll_until_terminal(client, first["analysis_id"])

        # And once complete, asking again returns the same result, not a new run.
        done = client.post(f"/api/v1/documents/{document_id}/analyze")
        assert done.status_code == 200
        assert done.json()["reused"] is True
        assert len(provider.calls) == 1

    def test_two_documents_do_not_share_an_analysis(self, client, use_provider):
        provider = use_provider(FakeProvider())
        first_id = upload(client, contract_pdf()).json()["document_id"]
        second_id = upload(client, contract_pdf()).json()["document_id"]
        assert first_id != second_id

        for document_id in (first_id, second_id):
            client.post(f"/api/v1/documents/{document_id}/extract")

        first = client.post(f"/api/v1/documents/{first_id}/analyze").json()
        second = client.post(f"/api/v1/documents/{second_id}/analyze").json()
        assert first["analysis_id"] != second["analysis_id"]

        poll_until_terminal(client, first["analysis_id"])
        poll_until_terminal(client, second["analysis_id"])

        for document_id, analysis in ((first_id, first), (second_id, second)):
            body = client.get(f"/api/v1/documents/{document_id}/findings").json()
            assert body["analysis_id"] == analysis["analysis_id"]
            assert body["document_id"] == document_id
        assert len(provider.calls) == 2


class TestPublishedContract:
    """What the API actually produces, pinned so documentation cannot drift.

    `DocumentStatus` declares the full workflow state machine from
    docs/02_ARCHITECTURE.md sec. 4. Only part of it belongs to the *document*
    resource: from Phase 7, analysis progress is a separate resource with its
    own `AnalysisStatus` and `AnalysisStage`, so there is one source of truth
    for it rather than two that can disagree. This test records which states
    the document endpoints can really return.
    """

    REACHABLE_DOCUMENT_STATUSES = {"validated", "extracting", "ingested", "ingestion_failed"}

    def test_document_status_values_are_the_documented_ones(self, client, use_provider):
        use_provider(FakeProvider())
        seen = set()

        document_id = upload(client, contract_pdf()).json()["document_id"]
        seen.add(client.get(f"/api/v1/documents/{document_id}/status").json()["status"])
        client.post(f"/api/v1/documents/{document_id}/extract")
        seen.add(client.get(f"/api/v1/documents/{document_id}/status").json()["status"])

        # A document nothing could be read from.
        broken_id = upload(
            client, make_pdf_with_image_only_page(1, image_page=1)
        ).json()["document_id"]
        client.post(f"/api/v1/documents/{broken_id}/extract")
        seen.add(client.get(f"/api/v1/documents/{broken_id}/status").json()["status"])

        assert seen <= self.REACHABLE_DOCUMENT_STATUSES
        assert {"validated", "ingested"} <= seen

    def test_analysis_progress_is_not_mirrored_onto_the_document(self, client, use_provider):
        """One source of truth: the document never claims to be "analyzing"."""
        use_provider(FakeProvider(delay=0.4))
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")
        analysis_id = client.post(
            f"/api/v1/documents/{document_id}/analyze"
        ).json()["analysis_id"]

        during = client.get(f"/api/v1/documents/{document_id}/status").json()["status"]
        poll_until_terminal(client, analysis_id)
        after = client.get(f"/api/v1/documents/{document_id}/status").json()["status"]

        assert during in self.REACHABLE_DOCUMENT_STATUSES
        assert after in self.REACHABLE_DOCUMENT_STATUSES

    def test_health_reports_configuration_without_the_key(self, client):
        body = client.get("/api/v1/health").json()

        assert body["status"] == "ok"
        assert isinstance(body["model_provider_configured"], bool)
        assert "nvapi" not in str(body)
        assert "key" not in str(body).lower().replace("model_provider_configured", "")
