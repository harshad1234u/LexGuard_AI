"""Page-level PDF text extraction.

Each page is extracted independently so that a failure on one page cannot
silently take the rest of the document with it. The result is a per-page record
with an explicit status - the application's own evidence of what it actually
read (docs/01_PRD.md sec. 8).

Extraction is kept behind the `PageExtractor` protocol so an OCR path can be
added later (docs/09_DECISIONS.md: "OCR ... fallback only if needed") without
touching ingestion, the manifest, or the coverage controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import fitz  # PyMuPDF

from app.core.logging import get_logger

logger = get_logger(__name__)


class PageStatus(StrEnum):
    """Outcome of extracting a single page."""

    PROCESSED = "processed"
    """Text was extracted successfully."""

    EMPTY = "empty"
    """No text and no images - a genuinely blank page. Counts as covered."""

    UNREADABLE = "unreadable"
    """No text, but the page carries images.

    Almost always a scanned page. The content exists but we did not capture it,
    so the page must NOT count towards complete coverage: claiming a complete
    analysis while a scanned clause went unread is exactly the failure this
    system exists to prevent. Resolving these pages is what an OCR path is for.
    """

    FAILED = "failed"
    """Extraction raised, or the page was absent from the document."""


#: Statuses where the application genuinely holds the page's content.
COVERED_STATUSES: frozenset[PageStatus] = frozenset({PageStatus.PROCESSED, PageStatus.EMPTY})


@dataclass
class ExtractedPage:
    """One page's extraction result, including its text.

    `text` stays in memory only (ADR-005) and is what the Phase 5 evidence
    verifier will check model quotes against.
    """

    page_number: int  # 1-based, as users and citations count pages
    status: PageStatus
    text: str = ""
    image_count: int = 0
    failure_reason: str | None = None
    extraction_method: str = "pymupdf_text"

    @property
    def text_length(self) -> int:
        return len(self.text)

    @property
    def is_covered(self) -> bool:
        return self.status in COVERED_STATUSES


class PageExtractor(Protocol):
    """Strategy for turning one PDF page into text."""

    name: str

    def extract(self, page: fitz.Page, page_number: int) -> ExtractedPage:
        """Extract `page`. May raise; the caller records the failure."""
        ...


class PyMuPDFTextExtractor:
    """Default extractor: PyMuPDF's native text layer.

    Fast and exact for digital PDFs, and returns nothing for scanned pages -
    which is why image-bearing pages with no text are reported UNREADABLE
    rather than quietly treated as blank.
    """

    name = "pymupdf_text"

    def extract(self, page: fitz.Page, page_number: int) -> ExtractedPage:
        text = page.get_text("text") or ""
        stripped = text.strip()

        if stripped:
            status = PageStatus.PROCESSED
        else:
            # Distinguish a blank page from one we simply could not read.
            image_count = len(page.get_images(full=True))
            return ExtractedPage(
                page_number=page_number,
                status=PageStatus.UNREADABLE if image_count else PageStatus.EMPTY,
                text="",
                image_count=image_count,
                failure_reason="no_text_layer" if image_count else None,
                extraction_method=self.name,
            )

        return ExtractedPage(
            page_number=page_number,
            status=status,
            text=text,
            image_count=len(page.get_images(full=True)),
            extraction_method=self.name,
        )


def extract_pages(
    source_path: Path,
    *,
    expected_pages: int,
    extractor: PageExtractor | None = None,
) -> list[ExtractedPage]:
    """Extract every expected page, one at a time.

    Always returns exactly `expected_pages` records. A page that raises, or that
    the reopened document no longer contains, is recorded as FAILED rather than
    omitted - a short list would understate the document and let a partial read
    masquerade as a whole one.
    """
    extractor = extractor or PyMuPDFTextExtractor()
    pages: list[ExtractedPage] = []

    try:
        document = fitz.open(source_path)
    except Exception as exc:
        logger.warning("document open failed during extraction type=%s", type(exc).__name__)
        return [
            ExtractedPage(
                page_number=number,
                status=PageStatus.FAILED,
                failure_reason="document_unreadable",
                extraction_method=extractor.name,
            )
            for number in range(1, expected_pages + 1)
        ]

    try:
        available = document.page_count
        for page_number in range(1, expected_pages + 1):
            if page_number > available:
                # The PDF claimed more pages than it now yields.
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        status=PageStatus.FAILED,
                        failure_reason="page_missing",
                        extraction_method=extractor.name,
                    )
                )
                continue

            try:
                pages.append(extractor.extract(document.load_page(page_number - 1), page_number))
            except Exception as exc:
                # One bad page must not abort the document.
                logger.warning(
                    "page extraction failed page=%d type=%s", page_number, type(exc).__name__
                )
                pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        status=PageStatus.FAILED,
                        failure_reason=type(exc).__name__,
                        extraction_method=extractor.name,
                    )
                )
    finally:
        document.close()

    return pages
