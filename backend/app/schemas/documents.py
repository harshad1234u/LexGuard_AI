"""API schemas for the document lifecycle.

These mirror the contract in docs/07_API_SPEC.md. The state names follow the
workflow state machine in docs/02_ARCHITECTURE.md sec. 4.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    """Workflow states. No failure state may transition to READY."""

    # --- Success path ---
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    EXTRACTING = "extracting"
    INGESTED = "ingested"
    COVERAGE_VERIFIED = "coverage_verified"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    EVIDENCE_VERIFIED = "evidence_verified"
    OUTPUT_VALIDATED = "output_validated"
    READY = "ready"

    # --- Failure states ---
    VALIDATION_FAILED = "validation_failed"
    INGESTION_FAILED = "ingestion_failed"
    INCOMPLETE_DOCUMENT = "incomplete_document"
    EVIDENCE_MISMATCH = "evidence_mismatch"
    OUTPUT_REJECTED = "output_rejected"


TERMINAL_FAILURE_STATES: frozenset[DocumentStatus] = frozenset(
    {
        DocumentStatus.VALIDATION_FAILED,
        DocumentStatus.INGESTION_FAILED,
        DocumentStatus.INCOMPLETE_DOCUMENT,
        DocumentStatus.EVIDENCE_MISMATCH,
        DocumentStatus.OUTPUT_REJECTED,
    }
)


class CoverageStatus(StrEnum):
    """Application-level coverage verdict. Never taken from the model."""

    PENDING = "pending"
    """Validated, but pages have not been extracted yet."""

    PROCESSING = "processing"
    """Extraction is underway."""

    COMPLETE = "complete"
    """Every page was processed and the source is trustworthy. Only this value
    permits a complete-document analysis."""

    INCOMPLETE = "incomplete"
    """Part of the document was not captured."""

    FAILED = "failed"
    """Nothing usable could be read."""

    BLOCKED_REPAIRED = "blocked_repaired"
    """All recoverable pages were read, but the PDF had to be repaired, so the
    page count itself cannot be trusted. Never eligible for complete analysis."""


class UploadResponse(BaseModel):
    """Response for POST /api/v1/documents/upload."""

    document_id: str
    filename: str = Field(description="Sanitised original filename.")
    page_count: int
    size_bytes: int
    content_type: str
    status: DocumentStatus
    source_repaired: bool = Field(
        default=False,
        description=(
            "True when the PDF had to be structurally repaired to be read. The page "
            "count may then be lower than the original document."
        ),
    )


class StatusResponse(BaseModel):
    """Response for GET /api/v1/documents/{document_id}/status.

    `expected_pages` vs `processed_pages` is the coverage invariant from
    docs/04_SECURITY_GROUNDING.md sec. 12 and is computed by the application.
    """

    document_id: str
    status: DocumentStatus
    expected_pages: int
    processed_pages: int = Field(
        description="Pages whose content the application actually holds. Unreadable and failed pages are excluded."
    )
    failed_pages: list[int] = Field(default_factory=list)
    unreadable_pages: list[int] = Field(
        default_factory=list,
        description="Pages carrying images but no text layer - almost always scanned pages whose content was not captured.",
    )
    coverage_status: CoverageStatus
    coverage_explanation: str = Field(
        default="",
        description="Plain-language reason for the coverage verdict.",
    )
    analysis_eligible: bool = Field(
        default=False,
        description=(
            "Whether this document may receive a complete-document analysis. False blocks the "
            "model from being invoked for one at all."
        ),
    )
    source_repaired: bool = False


class ValueKind(StrEnum):
    """Kinds of value the application can locate deterministically.

    A kind says what sort of token was found, never what it means. Nothing here
    implies that a value is a deadline, an obligation or a risk - establishing
    that is interpretation, and interpretation belongs to the verified-findings
    path (docs/01_PRD.md sec. 4.3).
    """

    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    DURATION = "duration"
    DATE = "date"


class DocumentValue(BaseModel):
    """One value the application located in the document, bound to its page."""

    kind: ValueKind
    value: str = Field(
        description="The value as the document writes it. Never paraphrased, never resolved."
    )
    page: int = Field(description="1-based page the value was found on.")
    ambiguous: bool = Field(
        default=False,
        description=(
            "Dates only. True when the written form has more than one reading, in which "
            "case it is reported as written and no calendar meaning is assigned."
        ),
    )


class ValuesExtraction(BaseModel):
    """How much text the application actually read, as counts only.

    This exists so that an empty value list can be explained rather than merely
    reported. Two very different documents produce `values: []`:

        a contract the application read in full that states no amounts
        a document from which no text could be recovered at all

    Telling a reader the second is the first would be a quiet false negative -
    it would present "nothing was found" as a fact about the document when it
    is really a fact about the extraction. Coverage cannot settle it either: a
    PDF whose pages carry neither text nor images is `complete` and empty.

    Counts only - never text, never a sample, never a filename. These are the
    same numbers the manifest already holds, so the two cannot disagree.
    """

    characters: int = Field(
        ge=0,
        description="Total characters extracted across every page. 0 means nothing was read.",
    )
    pages_with_text: int = Field(
        ge=0, description="Pages that yielded any text at all."
    )
    pages_total: int = Field(ge=0, description="Pages the document was expected to have.")

    @property
    def has_text(self) -> bool:
        """Whether the application recovered any text to search at all."""
        return self.characters > 0


class ValuesResponse(BaseModel):
    """Response for GET /api/v1/documents/{document_id}/values.

    A deterministic index of the document's own text. **No model is involved**,
    so nothing here is a claim to be verified - and nothing here is a summary,
    a risk assessment or a statement about what the document requires.
    """

    document_id: str
    coverage_status: CoverageStatus
    extraction: ValuesExtraction = Field(
        description=(
            "What was read, so an empty list can be told apart from an unread document. "
            "Counts only - no document text."
        )
    )
    values: list[DocumentValue] = Field(
        default_factory=list,
        description=(
            "Every supported value found, ordered by page. Deduplicated within a page, "
            "never across pages. An empty list means none were detected, not that the "
            "document contains none."
        ),
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str
    version: str
    model_provider_configured: bool = Field(
        description="Whether a server-side model API key is present. The key itself is never returned."
    )

    model_config = {"protected_namespaces": ()}

