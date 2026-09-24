"""The workflow's typed state.

Only what the nodes need to pass to one another. Two things are deliberately
absent:

* Document text. `DocumentRecord` remains the single authoritative source of
  document content; the state carries page *numbers*, and any node needing the
  text asks the store for it. Copying pages in here would create a second
  source of truth and put legal text into anything that serialises state.
* Secrets. No key, no client, no provider object.
"""

from __future__ import annotations

from typing import TypedDict

from app.models.reasoning import ModelReasoning, ReasoningFindingInput
from app.schemas.analysis import (
    AnalysisStage,
    CoverageSummary,
    ErrorCategory,
    ReasoningNoteOut,
    ReasoningStatus,
)
from app.schemas.findings import LanguageCode
from app.schemas.findings import ModelAnalysis, VerifiedFinding
from app.verification.policy import ReleaseOutcome


class AnalysisState(TypedDict, total=False):
    """State threaded through the analysis graph."""

    # --- Identity ------------------------------------------------------
    analysis_id: str
    document_id: str
    stage: AnalysisStage

    # --- Ingestion / coverage -------------------------------------------
    coverage: CoverageSummary
    coverage_complete: bool
    """Set only by the coverage gate node. The single flag the graph branches on."""

    # --- Document map ----------------------------------------------------
    supplied_pages: list[int]
    """Page numbers sent to the model. Never text - the store holds that."""

    # --- Model ------------------------------------------------------------
    proposed_count: int
    """How many findings the model proposed. Proposals, not facts."""

    model_analysis: ModelAnalysis
    """The model's raw proposal, in flight between the model and verification
    nodes. It contains quoted document text because evidence quotes *are* the
    proposal - that is the thing being checked. It is held in memory for the
    duration of the run, never logged, and never returned to a client; only
    findings that pass the output gate reach a response."""

    # --- Verification -----------------------------------------------------
    verified_findings: list[VerifiedFinding]
    """Every proposal paired with its verdict, before gating."""

    # --- Output gate -------------------------------------------------------
    release_outcome: ReleaseOutcome
    """What the output policy decided. Set only by `output_gate_node`, and the
    only thing `build_result` is allowed to publish - so a run that never
    reached the trust boundary returns no findings rather than the model's
    unchecked proposal."""

    displayable_count: int
    withheld_count: int

    # --- Request / provenance (Phase 23) --------------------------------------
    language: LanguageCode
    """The reader's language. Only translations follow it."""

    provider_name: str
    provider_model: str
    deadline: float
    """`time.monotonic()` by which the whole run must end. The reasoning stage
    uses it to skip itself rather than push a finished analysis past its budget."""

    # --- Reasoning (Phase 23; after the output gate, never before it) ----------
    reasoning_input: tuple[ReasoningFindingInput, ...]
    """Frozen copy of the released findings - the reasoning provider's entire view."""

    reasoning_proposal: ModelReasoning
    reasoning_status: ReasoningStatus
    reasoning_failure_kind: str
    reasoning_provider_name: str
    reasoning_provider_model: str
    reasoning_notes: list[ReasoningNoteOut]
    reasoning_withheld: int

    # --- Failure ------------------------------------------------------------
    error_category: ErrorCategory
    error_message: str
    provider_failure_kind: str
    """A fixed `ProviderFailureKind` value. Logs, provenance and audit only."""
    """Plain-language and safe to show. Never provider or exception text."""


def has_failed(state: AnalysisState) -> bool:
    """Whether a node has recorded a failure.

    Every stage transition consults this, so one failed node ends the run
    rather than letting later nodes work on unusable state.
    """
    return bool(state.get("error_category"))


def fail(
    state: AnalysisState,
    category: ErrorCategory,
    message: str,
) -> AnalysisState:
    """Record a terminal failure as a state update."""
    return {"error_category": category, "error_message": message}
