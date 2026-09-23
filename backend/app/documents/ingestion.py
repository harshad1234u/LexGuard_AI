"""Ingestion: extraction -> manifest -> coverage verdict.

This is the single place a document moves from "validated" to "we know exactly
what we read". It drives the lifecycle

    validated -> extracting -> ingested | ingestion_failed

and leaves the record carrying a manifest, the per-page text, and a coverage
report produced by the coverage controller. No model is involved: Phase 3 and
Phase 4 are entirely local and deterministic.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.documents.extraction import PageExtractor, extract_pages
from app.documents.manifest import DocumentManifest, build_manifest
from app.documents.storage import DocumentRecord
from app.schemas.documents import CoverageStatus, DocumentStatus
from app.verification.coverage import CoverageReport, check_coverage

logger = get_logger(__name__)


def ingest_document(
    record: DocumentRecord,
    *,
    extractor: PageExtractor | None = None,
) -> tuple[DocumentManifest, CoverageReport]:
    """Extract every page of `record`, build its manifest, and rate coverage.

    Safe to call more than once; a re-run simply replaces the previous result.
    """
    record.status = DocumentStatus.EXTRACTING

    pages = extract_pages(
        record.source_path,
        expected_pages=record.page_count,
        extractor=extractor,
    )

    manifest = build_manifest(
        document_id=record.document_id,
        total_pages=record.page_count,
        is_repaired=record.is_repaired,
        pages=pages,
        extraction_method=pages[0].extraction_method if pages else "pymupdf_text",
    )
    report = check_coverage(manifest)

    record.attach_extraction(pages, manifest)
    record.status = (
        DocumentStatus.INGESTION_FAILED
        if report.status is CoverageStatus.FAILED
        else DocumentStatus.INGESTED
    )

    # Metadata only - page text never reaches the logs.
    logger.info(
        "extraction complete document_id=%s expected=%d processed=%d failed=%d "
        "unreadable=%d coverage=%s",
        record.document_id,
        report.expected_pages,
        report.processed_pages,
        len(report.failed_pages),
        len(report.unreadable_pages),
        report.status,
    )
    return manifest, report
