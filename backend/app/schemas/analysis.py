"""Schemas for the analysis workflow and its API surface.

An analysis is a job: started with one request, observed with another. The
shapes here are what a client may see, and they carry metadata only - no
prompts, no raw model output, no provider internals, no document text beyond
the evidence quotes a verified finding is built on.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.findings import AttentionLevel, Evidence, LanguageCode, VerificationStatus
from app.schemas.provenance import Provenance


class AnalysisStage(StrEnum):
    """Where in the workflow an analysis currently is.

    Mirrors the graph nodes, so a client can show honest progress rather than
    a spinner.
    """

    QUEUED = "queued"
    VALIDATING = "validating"
    INGESTING = "ingesting"
    CHECKING_COVERAGE = "checking_coverage"
    BUILDING_DOCUMENT_MAP = "building_document_map"
    ANALYZING = "analyzing"
    VERIFYING = "verifying"
    GATING_OUTPUT = "gating_output"
    DONE = "done"


class AnalysisStatus(StrEnum):
    """Terminal and non-terminal states of an analysis job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    """Reached the output gate and passed it. Never set on any other path."""

    FAILED = "failed"


TERMINAL_STATUSES: frozenset[AnalysisStatus] = frozenset(
    {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED}
)


class ErrorCategory(StrEnum):
    """Application-level failure categories.

    Deliberately coarse: enough for a client to say something useful, never
    enough to leak provider internals or a stack trace.
    """

    VALIDATION_ERROR = "validation_error"
    INGESTION_ERROR = "ingestion_error"
    COVERAGE_ERROR = "coverage_error"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    MODEL_OUTPUT_INVALID = "model_output_invalid"
    VERIFICATION_ERROR = "verification_error"
    ANALYSIS_TIMEOUT = "analysis_timeout"
    INTERNAL_ERROR = "internal_error"


class CoverageSummary(BaseModel):
    """The coverage facts the workflow acted on, as measured by the application."""

    status: str
    expected_pages: int
    processed_pages: int
    failed_pages: list[int] = Field(default_factory=list)
    unreadable_pages: list[int] = Field(default_factory=list)
    source_repaired: bool = False


class VerifiedFindingOut(BaseModel):
    """A finding that passed the output gate.

    Only findings whose `verification_status` is `verified` are ever placed in
    a response's `findings` list, so this type always describes something the
    document supports.
    """

    id: str
    type: str = Field(
        description="Clause category. Model-chosen, bounded and refused if it reads as an instruction."
    )
    claim: str = Field(description="Verified against the document, claim by claim.")
    evidence: Evidence = Field(
        description=(
            "The quote, located in the document by the verifier. `section` is the model's "
            "citation and is present only when the cited page carries that exact label - "
            "an unconfirmable citation is dropped rather than shown."
        )
    )
    explanation: str = Field(
        default="",
        description=(
            "Plain-language interpretation. Released only when it does not contradict the "
            "quoted text; see `explanation_verified` for whether the evidence establishes it."
        ),
    )
    explanation_verified: bool = Field(
        default=False,
        description=(
            "Whether the quoted text establishes the explanation, as opposed to merely not "
            "contradicting it. False means the sentence is interpretation and a client must "
            "not present it as a verified fact about the document."
        ),
    )
    attention: AttentionLevel = Field(
        default=AttentionLevel.INFO,
        description=(
            "How much of a reader's attention the quoted text asks for, derived by the "
            "application from what that text contains - a prohibition, an obligation, a sum, "
            "a deadline, consequence vocabulary. Never supplied by the model, and not a "
            "legal risk assessment."
        ),
    )
    verification_status: VerificationStatus
    explanation_translation: str | None = Field(
        default=None,
        description=(
            "The explanation in the reader's requested language. NOT independently checked: "
            "present only when `explanation_verified` is true and every figure in it appears "
            "in the evidence. A client must label it as a translation."
        ),
    )
    explanation_translation_language: LanguageCode | None = None


class WithheldSummary(BaseModel):
    """What the output gate blocked, counted but not shown.

    Surfaced so a reader knows the model proposed more than was displayed -
    silence about withheld claims would misrepresent the analysis.
    """

    total: int = 0
    rejected: int = 0
    unverified: int = 0
    partially_verified: int = 0


class AnalysisResult(BaseModel):
    """The gated outcome of an analysis."""

    findings: list[VerifiedFindingOut] = Field(default_factory=list)
    withheld: WithheldSummary = Field(default_factory=WithheldSummary)
    proposed_count: int = 0
    insufficient_evidence: bool = Field(
        default=False,
        description="True when the model proposed findings but none survived verification.",
    )
    coverage: CoverageSummary | None = None
    language: LanguageCode = LanguageCode.EN
    provenance: Provenance | None = None
    reasoning: "ReasoningResult | None" = None


# ---------------------------------------------------------------------------
# Reasoning notes (Phase 23)
# ---------------------------------------------------------------------------

#: Set by the application on every note. Never model-supplied, never varied.
REASONING_NOTE_LABEL = "Reasoning note — not independently verified"


class ReasoningStatus(StrEnum):
    COMPLETED = "completed"
    DISABLED = "disabled"
    """REASONING_ENABLED=false or REASONING_PROVIDER=none."""
    SKIPPED = "skipped"
    """Fewer than two released findings, or too little of the analysis budget left."""
    UNAVAILABLE = "unavailable"
    """The reasoning provider is not configured."""
    FAILED = "failed"
    """The provider call failed. Findings are unaffected."""


class ReasoningNoteOut(BaseModel):
    """A model's observation relating released findings.

    Interpretation, not a fact about the document. There is deliberately no
    verification status here: `evidence_checked` says only that each quote is
    real text from the findings the note cites.
    """

    id: str
    category: str
    text: str
    finding_ids: list[str]
    quotes: list[str] = Field(default_factory=list)
    evidence_checked: bool = False
    label: str = REASONING_NOTE_LABEL


class ReasoningResult(BaseModel):
    status: ReasoningStatus
    failure_kind: str | None = Field(
        default=None, description="A fixed ProviderFailureKind value when status is failed/unavailable."
    )
    provider: str | None = None
    notes: list[ReasoningNoteOut] = Field(default_factory=list)
    withheld_count: int = 0


class AnalyzeRequest(BaseModel):
    """Optional body for POST /analyze. An empty body means English."""

    language: LanguageCode = LanguageCode.EN


class AnalyzeResponse(BaseModel):
    """Response for POST /api/v1/documents/{document_id}/analyze."""

    analysis_id: str
    document_id: str
    status: AnalysisStatus
    stage: AnalysisStage
    created_at: datetime
    reused: bool = Field(
        default=False,
        description="True when an existing analysis was returned instead of starting a new one.",
    )


class AnalysisStatusResponse(BaseModel):
    """Response for GET /api/v1/analysis/{analysis_id}/status."""

    analysis_id: str
    document_id: str
    status: AnalysisStatus
    stage: AnalysisStage
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    coverage: CoverageSummary | None = None
    proposed_count: int | None = None
    verified_count: int | None = None
    withheld_count: int | None = None
    error_category: ErrorCategory | None = None
    error_message: str | None = Field(
        default=None,
        description="Plain-language reason, safe to display. Never provider or stack detail.",
    )


# ---------------------------------------------------------------------------
# Document overview (Phase 21)
# ---------------------------------------------------------------------------
#
# A grouped view of findings that have ALREADY passed the output gate. It is a
# projection, not an analysis: its only input is `AnalysisResult.findings`, so
# a withheld finding is not merely excluded from it - it is not reachable from
# it. Nothing here is a summary of the document, and nothing here is a legal
# assessment.


class OverviewCategory(StrEnum):
    """The closed set of topics a released finding can be grouped under.

    Closed on purpose. The model chooses a free-form `type` for each finding
    and the release policy bounds that string, but a *category* is a heading
    the application publishes, so the model must not be able to invent one.
    Anything that does not map to a named topic lands in `OTHER`, which keeps
    the finding's own label beside it rather than discarding it.

    These are document topics, not legal classifications. "Liability" means
    the finding is about a clause the document words as a limitation of
    liability - not that the application has assessed any liability.
    """

    PARTIES = "parties_roles"
    FEES = "fees_payments"
    TERM = "term_renewal"
    TERMINATION = "termination"
    CONFIDENTIALITY = "confidentiality"
    LIABILITY = "liability"
    NOTICES = "notices"
    GOVERNING_LAW = "governing_law"
    OTHER = "other"


class OverviewItem(BaseModel):
    """One released finding, as the overview refers to it.

    Every field is copied verbatim from a `VerifiedFindingOut` already present
    in the same response. Nothing is reconstructed, paraphrased or re-derived.

    `explanation` and `attention` are deliberately absent. The explanation is
    interpretation the evidence does not necessarily establish, and it already
    carries its own label on the finding card; repeating it here, in a panel
    whose whole purpose is to show verified content, would blur the one
    distinction this product exists to keep. `attention` is not a risk
    assessment and is not rendered as one.
    """

    finding_id: str = Field(description="The `id` of the finding this refers to.")
    claim: str = Field(description="The verified claim, copied from the released finding.")
    quote: str = Field(description="The located evidence quote, copied from the released finding.")
    page: int = Field(description="The page the quote was located on.")
    section: str | None = Field(
        default=None,
        description=(
            "The citation, present only when the release policy confirmed it against the "
            "cited page. Absent otherwise - an unconfirmable citation is dropped, never shown."
        ),
    )
    label: str = Field(
        description=(
            "The finding's own category label, as published on the finding itself. Kept so a "
            "finding grouped under `other` still says what it is about."
        )
    )


class OverviewCategoryGroup(BaseModel):
    """One topic and the released findings grouped under it."""

    key: OverviewCategory
    label: str = Field(description="Display heading for the topic. Application-chosen.")
    items: list[OverviewItem] = Field(default_factory=list)
    empty_message: str | None = Field(
        default=None,
        description=(
            "Set only when `items` is empty. States that nothing was released for this topic "
            "and NOT that the document lacks it - the application cannot establish the absence "
            "of a clause, only that it confirmed nothing. Never contains claim text."
        ),
    )


class DocumentOverview(BaseModel):
    """Released findings, grouped by document topic.

    Not a summary. Not a checklist. Not a completeness statement about the
    document. A topic with no items means no finding about it survived
    verification, which is a fact about this analysis rather than about the
    agreement - the counts below are published alongside so a reader can see
    how much was proposed and how much was withheld.
    """

    categories: list[OverviewCategoryGroup] = Field(default_factory=list)
    released_count: int = Field(
        default=0, description="Findings that passed the output gate and are shown."
    )
    proposed_count: int = Field(
        default=0, description="Findings the model proposed, before verification."
    )
    withheld_count: int = Field(
        default=0,
        description="Findings the application refused to release. Counted here, never shown.",
    )


class FindingsResponse(BaseModel):
    """Response for GET /api/v1/documents/{document_id}/findings."""

    document_id: str
    analysis_id: str
    status: AnalysisStatus
    result: AnalysisResult
    overview: DocumentOverview = Field(
        default_factory=DocumentOverview,
        description=(
            "`result.findings`, grouped by topic. Additive and derived: every claim, quote, "
            "page and citation in it is already present in `result.findings`, so a client that "
            "ignores this field loses no information and gains no risk from it."
        ),
    )


AnalysisResult.model_rebuild()
