"""API-level tests for upload and status."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.errors import ErrorCode
from tests.conftest import make_pdf, upload


class TestUpload:
    def test_upload_returns_contract_fields(self, client, sample_pdf):
        response = upload(client, sample_pdf)
        assert response.status_code == 201
        body = response.json()
        assert body["document_id"].startswith("doc_")
        assert body["filename"] == "contract.pdf"
        assert body["page_count"] == 3
        assert body["status"] == "validated"
        assert body["source_repaired"] is False

    def test_repaired_pdf_is_reported_to_the_client(self, client):
        content = make_pdf(pages=5)
        body = upload(client, content[: len(content) // 3]).json()
        assert body["source_repaired"] is True
        status = client.get(f"/api/v1/documents/{body['document_id']}/status").json()
        assert status["source_repaired"] is True

    def test_document_ids_are_unique_and_unguessable(self, client, sample_pdf):
        first = upload(client, sample_pdf).json()["document_id"]
        second = upload(client, sample_pdf).json()["document_id"]
        assert first != second
        assert len(first) > 16

    def test_rejected_upload_returns_structured_error(self, client):
        response = upload(client, b"not a pdf at all", filename="bad.pdf")
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == ErrorCode.SIGNATURE_MISMATCH
        assert error["message"]

    def test_oversized_upload_returns_413(self, client):
        response = upload(client, b"%PDF-" + b"0" * (3 * 1024 * 1024))
        assert response.status_code == 413
        assert response.json()["error"]["code"] == ErrorCode.FILE_TOO_LARGE

    def test_missing_file_field_is_a_structured_error(self, client):
        response = client.post("/api/v1/documents/upload")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"

    def test_stored_file_is_named_by_id_not_by_user_filename(self, client, sample_pdf):
        body = upload(client, sample_pdf, filename="../../evil.pdf").json()
        workspace = get_settings().workspace_path / body["document_id"]
        assert [p.name for p in workspace.iterdir()] == ["source.pdf"]
        assert body["filename"] == "evil.pdf"


class TestStatus:
    def test_status_reports_application_measured_coverage(self, client, sample_pdf):
        document_id = upload(client, sample_pdf).json()["document_id"]
        body = client.get(f"/api/v1/documents/{document_id}/status").json()

        assert body["expected_pages"] == 3
        assert body["processed_pages"] == 0
        assert body["failed_pages"] == []
        # Nothing has been extracted yet, so coverage must not claim completeness.
        assert body["coverage_status"] == "pending"

    def test_unknown_document_returns_404(self, client):
        response = client.get("/api/v1/documents/doc_does_not_exist/status")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == ErrorCode.DOCUMENT_NOT_FOUND


class TestDeletion:
    def test_delete_removes_record_and_files(self, client, sample_pdf):
        document_id = upload(client, sample_pdf).json()["document_id"]
        directory: Path = get_settings().workspace_path / document_id
        assert directory.exists()

        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert not directory.exists()
        assert client.get(f"/api/v1/documents/{document_id}/status").status_code == 404


class TestHealth:
    def test_health_reports_status_without_leaking_the_key(self, client, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-super-secret-value")
        get_settings.cache_clear()

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["model_provider_configured"] is True
        assert "nvapi-super-secret-value" not in response.text
