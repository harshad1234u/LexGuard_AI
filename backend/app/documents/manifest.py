"""The document manifest - the application's own record of what it read.

The manifest is the answer to "did we actually process all 50 pages?", and it
is assembled from per-page extraction results. It is never informed by the
model: an LLM's assurance that it "read the whole document" is not evidence
(docs/01_PRD.md sec. 8, docs/04_SECURITY_GROUNDING.md sec. 12).

Page text is deliberately absent here. The manifest is metadata, safe to log
and to serialise to the client; the extracted text stays in memory on the
document record.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.documents.extraction import ExtractedPage, PageStatus


class PageRecord(BaseModel):
    """Per-page processing state."""

    page_number: int
    status: PageStatus
    text_length: int = 0
    image_count: int = 0
    failure_reason: str | None = None

    @classmethod
    def from_extracted(cls, page: ExtractedPage) -> PageRecord:
        return cls(
            page_number=page.page_number,
            status=page.status,
            text_length=page.text_length,
            image_count=page.image_count,
            failure_reason=page.failure_reason,
        )


class DocumentManifest(BaseModel):
    """Objective, application-measured summary of document processing."""

    document_id: str
    total_pages: int = Field(description="Page count read from the file itself, not from the model.")
    is_repaired: bool = Field(
        default=False,
        description="True when the PDF's structure had to be rebuilt to be read at all.",
    )
    extraction_method: str = "pymupdf_text"
    pages: list[PageRecord] = Field(default_factory=list)

    # --- Derived counters -------------------------------------------------
    @property
    def processed_pages(self) -> list[int]:
        """Pages whose content the application actually holds.

        Blank pages count: there was nothing to miss. Pages that are unreadable
        or failed do not.
        """
        return [p.page_number for p in self.pages if p.status in (PageStatus.PROCESSED, PageStatus.EMPTY)]

    @property
    def failed_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.status is PageStatus.FAILED]

    @property
    def unreadable_pages(self) -> list[int]:
        """Pages with images but no text layer - content we did not capture."""
        return [p.page_number for p in self.pages if p.status is PageStatus.UNREADABLE]

    @property
    def empty_pages(self) -> list[int]:
        return [p.page_number for p in self.pages if p.status is PageStatus.EMPTY]

    @property
    def total_text_length(self) -> int:
        return sum(p.text_length for p in self.pages)


def build_manifest(
    *,
    document_id: str,
    total_pages: int,
    is_repaired: bool,
    pages: list[ExtractedPage],
    extraction_method: str = "pymupdf_text",
) -> DocumentManifest:
    """Assemble a manifest from extraction results, ordered by page number."""
    return DocumentManifest(
        document_id=document_id,
        total_pages=total_pages,
        is_repaired=is_repaired,
        extraction_method=extraction_method,
        pages=[PageRecord.from_extracted(p) for p in sorted(pages, key=lambda p: p.page_number)],
    )
