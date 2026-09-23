"""API surface for extraction, manifest, and the coverage-aware status."""

from __future__ import annotations

from app.core.errors import ErrorCode
from tests.conftest import (
    make_pdf,
    make_pdf_with_blank_pages,
    make_pdf_with_image_only_page,
    upload,
)


def upload_and_extract(client, content: bytes):
    document_id = upload(client, content).json()["document_id"]
    response = client.post(f"/api/v1/documents/{document_id}/extract")
    return document_id, response


class TestExtractEndpoint:
    def test_extract_returns_manifest_and_coverage(self, client):
        _, response = upload_and_extract(client, make_pdf(pages=6))
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ingested"
        assert body["manifest"]["total_pages"] == 6
        assert len(body["manifest"]["pages"]) == 6
        assert body["coverage"]["status"] == "complete"
        assert body["coverage"]["processed_pages"] == 6

    def test_manifest_records_every_page_number_exactly_once(self, client):
        _, response = upload_and_extract(client, make_pdf(pages=20))
        numbers = [p["page_number"] for p in response.json()["manifest"]["pages"]]
        assert numbers == list(range(1, 21))

    def test_extract_on_unknown_document_is_404(self, client):
        response = client.post("/api/v1/documents/doc_nope/extract")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == ErrorCode.DOCUMENT_NOT_FOUND

    def test_page_text_is_never_returned_by_the_api(self, client):
        """The manifest is metadata; document content must not leak through it."""
        secret = "Confidential indemnity provision."
        _, response = upload_and_extract(client, make_pdf(pages=3, text=secret))
        assert "indemnity" not in response.text.lower()


class TestManifestEndpoint:
    def test_manifest_is_available_after_extraction(self, client):
        document_id, _ = upload_and_extract(client, make_pdf(pages=4))
        response = client.get(f"/api/v1/documents/{document_id}/manifest")

        assert response.status_code == 200
        assert response.json()["total_pages"] == 4

    def test_manifest_before_extraction_is_409(self, client):
        document_id = upload(client, make_pdf(pages=4)).json()["document_id"]
        response = client.get(f"/api/v1/documents/{document_id}/manifest")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == ErrorCode.COVERAGE_INCOMPLETE


class TestStatusAfterExtraction:
    def test_complete_document_is_analysis_eligible(self, client):
        document_id, _ = upload_and_extract(client, make_pdf(pages=8))
        body = client.get(f"/api/v1/documents/{document_id}/status").json()

        assert body["coverage_status"] == "complete"
        assert body["expected_pages"] == 8
        assert body["processed_pages"] == 8
        assert body["failed_pages"] == []
        assert body["unreadable_pages"] == []
        assert body["analysis_eligible"] is True

    def test_scanned_page_blocks_eligibility_and_says_why(self, client):
        document_id, _ = upload_and_extract(
            client, make_pdf_with_image_only_page(total=4, image_page=3)
        )
        body = client.get(f"/api/v1/documents/{document_id}/status").json()

        assert body["coverage_status"] == "incomplete"
        assert body["unreadable_pages"] == [3]
        assert body["processed_pages"] == 3
        assert body["analysis_eligible"] is False
        assert "scanned" in body["coverage_explanation"].lower()

    def test_repaired_document_is_never_eligible(self, client):
        content = make_pdf(pages=6)
        document_id, extract = upload_and_extract(client, content[: len(content) // 3])

        assert extract.json()["manifest"]["is_repaired"] is True

        body = client.get(f"/api/v1/documents/{document_id}/status").json()
        assert body["source_repaired"] is True
        assert body["coverage_status"] == "blocked_repaired"
        assert body["coverage_status"] != "complete"
        assert body["analysis_eligible"] is False
        assert "repaired" in body["coverage_explanation"].lower()

    def test_blank_pages_stay_eligible(self, client):
        document_id, _ = upload_and_extract(
            client, make_pdf_with_blank_pages(total=5, blank={2, 4})
        )
        body = client.get(f"/api/v1/documents/{document_id}/status").json()

        assert body["coverage_status"] == "complete"
        assert body["analysis_eligible"] is True

    def test_status_before_extraction_is_pending_and_ineligible(self, client):
        document_id = upload(client, make_pdf(pages=5)).json()["document_id"]
        body = client.get(f"/api/v1/documents/{document_id}/status").json()

        assert body["coverage_status"] == "pending"
        assert body["processed_pages"] == 0
        assert body["analysis_eligible"] is False

    def test_lifecycle_progresses_validated_then_ingested(self, client):
        document_id = upload(client, make_pdf(pages=3)).json()["document_id"]
        assert client.get(f"/api/v1/documents/{document_id}/status").json()["status"] == "validated"

        client.post(f"/api/v1/documents/{document_id}/extract")
        assert client.get(f"/api/v1/documents/{document_id}/status").json()["status"] == "ingested"


class TestQaEndpointReachesTheGate:
    """`/ask` arrived in Phase 9 (tests/test_api_qa.py covers it properly).

    What is asserted here is the boundary this file cares about: a document
    that has not been extracted cannot get an answer by skipping `/extract`.
    It reaches the coverage gate, not the model.
    """

    def test_ask_without_a_configured_provider_never_calls_out(self, client):
        document_id = upload(client, make_pdf()).json()["document_id"]
        response = client.post(
            f"/api/v1/documents/{document_id}/ask", json={"question": "What is the notice period?"}
        )
        # No provider is configured in tests, so the request fails offline
        # rather than reaching a vendor.
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_not_configured"
