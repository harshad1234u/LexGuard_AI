"""Ephemeral storage behaviour (ADR-005, FR-10)."""

from __future__ import annotations

import time

from app.core.config import get_settings
from app.documents.storage import document_store
from app.documents.validation import validate_upload
from tests.conftest import make_pdf


def _store_document(pages: int = 2):
    content = make_pdf(pages=pages)
    validated = validate_upload(
        filename="contract.pdf", content_type="application/pdf", content=content
    )
    return document_store.create(validated, content)


class TestRecordCoverageDelegation:
    """The record must not compute coverage itself; it delegates to the controller."""

    def test_fresh_record_is_pending(self):
        record = _store_document()
        assert record.manifest is None
        assert record.coverage.status == "pending"
        assert record.coverage.expected_pages == 2

    def test_record_reflects_controller_verdict_after_ingestion(self):
        from app.documents.ingestion import ingest_document

        record = _store_document(pages=4)
        ingest_document(record)
        assert record.coverage.status == "complete"
        assert record.coverage.processed_pages == 4


class TestExpiry:
    def test_expired_documents_are_purged_and_files_deleted(self, monkeypatch):
        monkeypatch.setenv("DOCUMENT_TTL_SECONDS", "0")
        get_settings.cache_clear()

        record = _store_document()
        directory = record.directory
        assert directory.exists()

        time.sleep(0.01)
        assert document_store.purge_expired() == 1
        assert not directory.exists()

    def test_clear_removes_every_working_directory(self):
        directories = [_store_document().directory for _ in range(3)]
        document_store.clear()
        assert not any(d.exists() for d in directories)
