"""Ephemeral document workspace (ADR-005: no permanent document storage).

Each accepted upload gets an isolated directory under the workspace root,
named by an opaque document id. Nothing about the original filename reaches
the filesystem. Records expire after `document_ttl_seconds` and expired
directories are removed, so uploaded legal documents do not outlive the
session that needed them.

The registry is in-process on purpose: the MVP has no database, and adding one
would mean persisting user legal documents (docs/02_ARCHITECTURE.md sec. 5.6).
"""

from __future__ import annotations

import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import ErrorCode, NotFoundError
from app.core.logging import get_logger
from app.documents.extraction import ExtractedPage
from app.documents.manifest import DocumentManifest
from app.documents.validation import ValidatedDocument
from app.schemas.documents import DocumentStatus
from app.verification.coverage import CoverageReport, check_coverage

logger = get_logger(__name__)

_STORED_FILENAME = "source.pdf"


@dataclass
class DocumentRecord:
    """Everything the application knows about one in-flight document.

    Extraction results are attached by `app.documents.ingestion`. Until then the
    manifest is None and coverage reports PENDING - a freshly uploaded document
    has been validated, not read.
    """

    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    page_count: int
    directory: Path
    status: DocumentStatus
    created_at: float
    is_repaired: bool = False
    manifest: DocumentManifest | None = None
    pages: list[ExtractedPage] = field(default_factory=list)
    """Per-page text, held in memory only. The Phase 5 verifier checks model
    quotes against this, and it is deleted with the record."""

    @property
    def source_path(self) -> Path:
        return self.directory / _STORED_FILENAME

    def attach_extraction(
        self, pages: list[ExtractedPage], manifest: DocumentManifest
    ) -> None:
        self.pages = pages
        self.manifest = manifest

    @property
    def coverage(self) -> CoverageReport:
        """Delegated to the coverage controller, the only authority on coverage."""
        return check_coverage(self.manifest, expected_pages=self.page_count)

    def page_text(self, page_number: int) -> str | None:
        """Extracted text for one page, or None if it was never captured."""
        for page in self.pages:
            if page.page_number == page_number:
                return page.text if page.is_covered else None
        return None


class DocumentStore:
    """Thread-safe registry of ephemeral document records."""

    def __init__(self) -> None:
        self._records: dict[str, DocumentRecord] = {}
        self._lock = threading.Lock()

    # --- Lifecycle -----------------------------------------------------
    def create(self, validated: ValidatedDocument, content: bytes) -> DocumentRecord:
        settings = get_settings()
        self.purge_expired()

        document_id = f"doc_{secrets.token_hex(12)}"
        directory = settings.workspace_path / document_id
        directory.mkdir(parents=True, exist_ok=True)

        record = DocumentRecord(
            document_id=document_id,
            filename=validated.filename,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            page_count=validated.page_count,
            is_repaired=validated.is_repaired,
            directory=directory,
            status=DocumentStatus.VALIDATED,
            created_at=time.time(),
        )
        record.source_path.write_bytes(content)

        with self._lock:
            self._records[document_id] = record

        # Metadata only - never the filename's full original form or content.
        logger.info(
            "document accepted document_id=%s pages=%d size_bytes=%d repaired=%s",
            document_id,
            record.page_count,
            record.size_bytes,
            record.is_repaired,
        )
        return record

    def get(self, document_id: str) -> DocumentRecord:
        self.purge_expired()
        with self._lock:
            record = self._records.get(document_id)
        if record is None:
            raise NotFoundError(
                ErrorCode.DOCUMENT_NOT_FOUND,
                "That document is not available. It may have expired; please upload it again.",
            )
        return record

    def delete(self, document_id: str) -> None:
        with self._lock:
            record = self._records.pop(document_id, None)
        if record is not None:
            self._remove_directory(record)

    def purge_expired(self) -> int:
        """Drop records past their TTL and delete their working directories."""
        ttl = get_settings().document_ttl_seconds
        cutoff = time.time() - ttl
        with self._lock:
            expired = [r for r in self._records.values() if r.created_at < cutoff]
            for record in expired:
                self._records.pop(record.document_id, None)
        for record in expired:
            self._remove_directory(record)
            logger.info("document expired document_id=%s", record.document_id)
        if expired:
            # Expiry reaches persisted metadata too. A no-op when persistence
            # is disabled; imported here to keep storage free of that import
            # at module load.
            from app.persistence import get_repository

            repository = get_repository()
            for record in expired:
                repository.delete_document(record.document_id)
        return len(expired)

    def clear(self) -> None:
        """Remove every record. Used on shutdown and by tests."""
        with self._lock:
            records = list(self._records.values())
            self._records.clear()
        for record in records:
            self._remove_directory(record)

    # --- Internals -----------------------------------------------------
    @staticmethod
    def _remove_directory(record: DocumentRecord) -> None:
        shutil.rmtree(record.directory, ignore_errors=True)


document_store = DocumentStore()
