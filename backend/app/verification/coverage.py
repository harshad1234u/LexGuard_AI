"""Coverage controller - the single authority on whether a document was fully read.

Nothing else in the application may decide coverage. The rule
(docs/04_SECURITY_GROUNDING.md sec. 12) is:

    FINAL_DOCUMENT_ANALYSIS => expected_pages == successfully_processed_pages

with one addition established during Phase 2: a PDF that PyMuPDF had to repair
can never reach COMPLETE. Its reported page count is itself reconstructed, so
"we processed all the pages we could see" says nothing about how many pages the
user's original document had. Extracting every recoverable page is not the same
as having read the document.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.errors import AppError, ErrorCode
from app.documents.manifest import DocumentManifest
from app.schemas.documents import CoverageStatus


class BlockingReason(StrEnum):
    """Why a document is not eligible for a complete-document analysis."""

    NOT_EXTRACTED = "not_extracted"
    NO_PAGES = "no_pages"
    PAGES_FAILED = "pages_failed"
    PAGES_UNREADABLE = "pages_unreadable"
    PAGES_MISSING = "pages_missing"
    SOURCE_REPAIRED = "source_repaired"


#: Human-readable explanations, safe to show a non-technical user.
REASON_MESSAGES: dict[BlockingReason, str] = {
    BlockingReason.NOT_EXTRACTED: "The document's pages have not been extracted yet.",
    BlockingReason.NO_PAGES: "No pages could be read from this document.",
    BlockingReason.PAGES_FAILED: "Some pages could not be processed.",
    BlockingReason.PAGES_UNREADABLE: (
        "Some pages contain images with no readable text, so their content was not captured. "
        "They are most likely scanned."
    ),
    BlockingReason.PAGES_MISSING: "Some pages the document claims to contain are missing.",
    BlockingReason.SOURCE_REPAIRED: (
        "This PDF was damaged and had to be repaired before it could be read, so its page "
        "count cannot be trusted."
    ),
}


class CoverageReport(BaseModel):
    """The verdict, plus the counts it was derived from."""

    status: CoverageStatus
    expected_pages: int
    processed_pages: int
    failed_pages: list[int] = Field(default_factory=list)
    unreadable_pages: list[int] = Field(default_factory=list)
    blocking_reasons: list[BlockingReason] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status is CoverageStatus.COMPLETE

    @property
    def explanation(self) -> str:
        if self.is_complete:
            return "Every page of this document was processed."
        if not self.blocking_reasons:
            return "This document is not eligible for a complete-document analysis."
        return " ".join(REASON_MESSAGES[reason] for reason in self.blocking_reasons)


class CoverageGateError(AppError):
    """Raised when an operation requiring complete coverage is attempted without it."""

    status_code = 409


def pending_report(expected_pages: int) -> CoverageReport:
    """The verdict for a document that has been validated but not yet extracted."""
    return CoverageReport(
        status=CoverageStatus.PENDING,
        expected_pages=expected_pages,
        processed_pages=0,
        blocking_reasons=[BlockingReason.NOT_EXTRACTED],
    )


def check_coverage(manifest: DocumentManifest | None, *, expected_pages: int = 0) -> CoverageReport:
    """Evaluate coverage from the manifest alone.

    Status precedence, most severe first: FAILED (nothing usable was read),
    INCOMPLETE (part of the document is missing), BLOCKED_REPAIRED (everything
    readable was read, but the source itself is untrustworthy), COMPLETE.
    """
    if manifest is None:
        return pending_report(expected_pages)

    processed = manifest.processed_pages
    failed = manifest.failed_pages
    unreadable = manifest.unreadable_pages
    missing = [
        p.page_number for p in manifest.pages if p.failure_reason == "page_missing"
    ]

    reasons: list[BlockingReason] = []
    if manifest.total_pages <= 0:
        reasons.append(BlockingReason.NO_PAGES)
    if missing:
        reasons.append(BlockingReason.PAGES_MISSING)
    if failed and set(failed) != set(missing):
        reasons.append(BlockingReason.PAGES_FAILED)
    if unreadable:
        reasons.append(BlockingReason.PAGES_UNREADABLE)
    if manifest.is_repaired:
        reasons.append(BlockingReason.SOURCE_REPAIRED)

    if manifest.total_pages <= 0 or (manifest.pages and not processed):
        status = CoverageStatus.FAILED
    elif failed or unreadable or len(processed) != manifest.total_pages:
        status = CoverageStatus.INCOMPLETE
    elif manifest.is_repaired:
        # Every recoverable page was read - but the source was rebuilt to get
        # there, so completeness cannot be claimed.
        status = CoverageStatus.BLOCKED_REPAIRED
    else:
        status = CoverageStatus.COMPLETE

    return CoverageReport(
        status=status,
        expected_pages=manifest.total_pages,
        processed_pages=len(processed),
        failed_pages=failed,
        unreadable_pages=unreadable,
        blocking_reasons=reasons,
    )


def require_complete_coverage(report: CoverageReport) -> None:
    """Hard gate. Raise unless the document is eligible for complete analysis.

    Every path that would present a complete-document result - and, from Phase 7,
    every call that would invoke the model for one - must pass through here
    first. The model is not asked whether the document was fully read; it is not
    invoked at all until this returns.
    """
    if report.is_complete:
        return

    raise CoverageGateError(
        ErrorCode.COVERAGE_INCOMPLETE,
        report.explanation,
        details={
            "coverage_status": str(report.status),
            "expected_pages": report.expected_pages,
            "processed_pages": report.processed_pages,
            "failed_pages": report.failed_pages,
            "unreadable_pages": report.unreadable_pages,
            "blocking_reasons": [str(r) for r in report.blocking_reasons],
        },
    )
