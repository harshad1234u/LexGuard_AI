"""Workflow nodes.

Each node does one thing, reuses the phase that already implements it, and
returns a state update. No node re-implements validation, extraction, coverage
or verification - they call the existing modules, so there is exactly one
implementation of each rule in the system.

The ordering constraint that matters most: `coverage_gate` sits between
`ingest` and `build_document_map`, and the graph will not reach the model node
unless it passes. That is enforced by the graph's edges, not by a check inside
the model node, so there is no path that calls a provider with an unverified
document.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.documents.ingestion import ingest_document
from app.documents.storage import DocumentRecord, document_store
from app.models.errors import (
    ModelAuthError,
    ModelError,
    ModelNotConfiguredError,
    ModelNotFoundError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from app.models.payload import build_payload
from app.models.provider import AnalysisRequest, ModelProvider
from app.schemas.analysis import (
    AnalysisResult,
    AnalysisStage,
    CoverageSummary,
    ErrorCategory,
    VerifiedFindingOut,
    WithheldSummary,
)
from app.schemas.findings import ModelAnalysis, VerificationStatus
from app.agents.state import AnalysisState, fail
from app.verification.coverage import CoverageGateError, require_complete_coverage
from app.verification.findings import verify_analysis_claims
from app.verification.policy import release_findings

logger = get_logger(__name__)

#: Provider failures mapped onto the categories a client may see. The provider's
#: own exception text never travels with them.
PROVIDER_ERROR_CATEGORIES: dict[type[ModelError], ErrorCategory] = {
    ModelNotConfiguredError: ErrorCategory.PROVIDER_NOT_CONFIGURED,
    ModelAuthError: ErrorCategory.PROVIDER_UNAVAILABLE,
    ModelNotFoundError: ErrorCategory.PROVIDER_UNAVAILABLE,
    ModelUnavailableError: ErrorCategory.PROVIDER_UNAVAILABLE,
    ModelTimeoutError: ErrorCategory.PROVIDER_TIMEOUT,
    ModelRateLimitError: ErrorCategory.PROVIDER_RATE_LIMITED,
    ModelResponseError: ErrorCategory.MODEL_OUTPUT_INVALID,
}


def _log(state: AnalysisState, event: str, **extra) -> None:
    """Metadata only. No document text, no prompts, no model output, no keys."""
    logger.info(
        "analysis %s analysis_id=%s document_id=%s%s",
        event,
        state.get("analysis_id"),
        state.get("document_id"),
        "".join(f" {k}={v}" for k, v in extra.items()),
    )


def _record(state: AnalysisState) -> DocumentRecord:
    return document_store.get(state["document_id"])


# --- 1. validate -----------------------------------------------------------
def validate_node(state: AnalysisState) -> AnalysisState:
    """Confirm the document exists and is analysable.

    Phase 2 already validated the file at upload; a document in the store has
    passed that. What is checked here is that it is still present and has
    pages - not a second copy of the upload rules.
    """
    update: AnalysisState = {"stage": AnalysisStage.VALIDATING}
    try:
        record = _record(state)
    except Exception:
        _log(state, "validate_failed", reason="document_not_found")
        return {**update, **fail(state, ErrorCategory.VALIDATION_ERROR,
                                "That document is no longer available. Please upload it again.")}

    if record.page_count <= 0:
        _log(state, "validate_failed", reason="no_pages")
        return {**update, **fail(state, ErrorCategory.VALIDATION_ERROR,
                                 "This document contains no pages to analyse.")}

    _log(state, "validated", pages=record.page_count)
    return update


# --- 2. ingest --------------------------------------------------------------
def ingest_node(state: AnalysisState) -> AnalysisState:
    """Ensure page-level extraction exists, reusing the Phase 3 pipeline."""
    update: AnalysisState = {"stage": AnalysisStage.INGESTING}
    record = _record(state)

    try:
        if record.manifest is None:
            ingest_document(record)
    except Exception as exc:
        _log(state, "ingest_failed", reason=type(exc).__name__)
        return {**update, **fail(state, ErrorCategory.INGESTION_ERROR,
                                 "The document's pages could not be read.")}

    coverage = record.coverage
    summary = CoverageSummary(
        status=str(coverage.status),
        expected_pages=coverage.expected_pages,
        processed_pages=coverage.processed_pages,
        failed_pages=sorted(coverage.failed_pages),
        unreadable_pages=sorted(coverage.unreadable_pages),
        source_repaired=record.is_repaired,
    )

    _log(
        state,
        "ingested",
        expected=summary.expected_pages,
        processed=summary.processed_pages,
        failed=len(summary.failed_pages),
        unreadable=len(summary.unreadable_pages),
        repaired=summary.source_repaired,
    )
    return {**update, "coverage": summary}


# --- 3. coverage gate --------------------------------------------------------
def coverage_gate_node(state: AnalysisState) -> AnalysisState:
    """The hard gate. Delegates entirely to the Phase 4 controller.

    No coverage rule is evaluated here. `require_complete_coverage` is the only
    implementation, so `blocked_repaired`, `incomplete`, `failed` and pages that
    were never readable are all refused by the same logic the status endpoint
    reports - and the graph stops before the model node exists as an option.
    """
    update: AnalysisState = {"stage": AnalysisStage.CHECKING_COVERAGE}
    record = _record(state)

    try:
        require_complete_coverage(record.coverage)
    except CoverageGateError as exc:
        _log(state, "coverage_blocked", coverage=record.coverage.status)
        return {
            **update,
            "coverage_complete": False,
            **fail(state, ErrorCategory.COVERAGE_ERROR, exc.message),
        }

    _log(state, "coverage_passed", pages=record.coverage.processed_pages)
    return {**update, "coverage_complete": True}


# --- 4. document map ----------------------------------------------------------
def build_document_map_node(state: AnalysisState) -> AnalysisState:
    """Record which pages will be supplied to the model.

    The payload itself is rebuilt in the model node from the authoritative
    store; what is kept here is the page list, so the state says exactly what
    the model was shown. Page identity is preserved end to end: the model cites
    a page number and the verifier looks up that same number.

    No retrieval, no chunking, no embeddings. A whole document with its page
    boundaries intact is the map.
    """
    update: AnalysisState = {"stage": AnalysisStage.BUILDING_DOCUMENT_MAP}
    record = _record(state)
    payload = build_payload(record)

    if not payload.pages:
        _log(state, "document_map_empty")
        return {**update, **fail(state, ErrorCategory.INGESTION_ERROR,
                                 "No readable page content is available for this document.")}

    _log(state, "document_map_built", supplied_pages=len(payload.pages))
    return {**update, "supplied_pages": payload.supplied_page_numbers}


# --- 5. model ------------------------------------------------------------------
async def analyze_node(state: AnalysisState, provider: ModelProvider) -> AnalysisState:
    """Ask the model for findings.

    Reached only when the coverage gate passed. The provider is injected as the
    `ModelProvider` interface - this module imports no vendor class, so the
    workflow is unchanged by which model answers.

    No retry. A failed inference is a terminal failure the user can re-request.
    """
    update: AnalysisState = {"stage": AnalysisStage.ANALYZING}
    record = _record(state)
    payload = build_payload(record)

    # The map node settled which pages go to the model; if that no longer holds,
    # stop rather than silently analyse a different document than was gated.
    expected_pages = state.get("supplied_pages", [])
    if payload.supplied_page_numbers != expected_pages:
        _log(state, "document_map_changed")
        return {**update, **fail(state, ErrorCategory.INTERNAL_ERROR,
                                 "The document changed while it was being analysed.")}

    try:
        analysis = await provider.analyze_document(AnalysisRequest(payload=payload))
    except ModelError as exc:
        category = PROVIDER_ERROR_CATEGORIES.get(type(exc), ErrorCategory.PROVIDER_UNAVAILABLE)
        # The category is coarse by design - four provider failures share
        # `provider_unavailable`. `reason` is the provider's own diagnosis, a
        # fixed vocabulary set in `nemotron._diagnose`, and it is what makes an
        # analysis failure identifiable afterwards rather than merely recorded.
        # Never the upstream message: that can echo the document.
        _log(
            state,
            "model_failed",
            category=str(category),
            reason=exc.details.get("reason", "unspecified"),
        )
        # exc.message is already the provider's safe, user-facing text.
        return {**update, **fail(state, category, exc.message)}
    except Exception as exc:
        _log(state, "model_failed", category="internal", reason=type(exc).__name__)
        return {**update, **fail(state, ErrorCategory.INTERNAL_ERROR,
                                 "The analysis could not be completed.")}

    _log(state, "model_responded", proposed=len(analysis.findings))
    return {**update, "proposed_count": len(analysis.findings), "model_analysis": analysis}


# --- 6. verification --------------------------------------------------------------
def verify_node(state: AnalysisState) -> AnalysisState:
    """Run the verifier over the model's proposals.

    Two layers, in one call: the Phase 5 evidence checks (does the quote exist
    on the cited page, do the figures agree) and the Phase 14 claim checks
    (does the sentence the model wrote say what that quote says). Before Phase
    14 only the first ran here, and a finding whose claim reversed its own
    quote was returned as verified.

    The verifier is used exactly as it is. Nothing here inspects or adjusts a
    verdict; the graph's job is to route the result, not to negotiate with it.
    """
    update: AnalysisState = {"stage": AnalysisStage.VERIFYING}
    record = _record(state)
    analysis: ModelAnalysis = state.get("model_analysis") or ModelAnalysis()

    try:
        verified = verify_analysis_claims(analysis, record)
    except Exception as exc:
        _log(state, "verification_failed", reason=type(exc).__name__)
        return {**update, **fail(state, ErrorCategory.VERIFICATION_ERROR,
                                 "The findings could not be checked against the document.")}

    outcomes: dict[str, int] = {}
    for item in verified:
        key = str(item.verification.status)
        outcomes[key] = outcomes.get(key, 0) + 1

    _log(state, "verified", **outcomes)
    return {**update, "verified_findings": verified}


# --- 7. output gate ------------------------------------------------------------------
def output_gate_node(state: AnalysisState) -> AnalysisState:
    """The trust boundary.

    One call, to `release_findings`, which is the application's single release
    policy. A finding reaches a response only if it comes back from there, and
    every field it carries has been confirmed, derived or dropped by that
    policy - never carried over from the model untouched.

    The decision is made here, where the document is still in hand, and stored
    on the state. `build_result` renders it and cannot re-open it; a state that
    never reached this node produces no findings at all.
    """
    update: AnalysisState = {"stage": AnalysisStage.GATING_OUTPUT}
    verified = state.get("verified_findings", [])

    try:
        outcome = release_findings(verified, _record(state))
    except Exception as exc:
        # The document is unavailable, so nothing can be re-read and no
        # citation confirmed. Publishing unchecked findings is not the
        # fallback; publishing nothing is.
        _log(state, "output_gate_failed", reason=type(exc).__name__)
        return {**update, **fail(state, ErrorCategory.VERIFICATION_ERROR,
                                 "The findings could not be checked against the document.")}

    _log(
        state,
        "output_gated",
        displayed=len(outcome.released),
        withheld=len(outcome.withheld),
    )
    return {
        **update,
        "release_outcome": outcome,
        "displayable_count": len(outcome.released),
        "withheld_count": len(outcome.withheld),
        "stage": AnalysisStage.DONE,
    }


def build_result(state: AnalysisState) -> AnalysisResult:
    """Assemble the client-facing result by applying the output policy.

    Rendering only. The decision was made by the output policy in
    `output_gate_node`, and every field of every finding here comes from that
    decision - not from the model's proposal. Phase 15 found four
    model-controlled fields passing straight through this function: the
    citation, the risk level, the category and the explanation.

    A state with no release decision publishes nothing.
    """
    verified = state.get("verified_findings", [])
    outcome = state.get("release_outcome")

    if outcome is None:
        # No release decision was made, so there is nothing this function is
        # entitled to publish. A state that skipped the output gate fails
        # closed rather than falling back on the model's proposal.
        return AnalysisResult(
            findings=[],
            withheld=WithheldSummary(total=len(verified), unverified=len(verified)),
            proposed_count=len(verified),
            insufficient_evidence=bool(verified),
            coverage=state.get("coverage"),
        )

    findings = [
        VerifiedFindingOut(
            id=decision.finding.finding.id or f"f_{index:03d}",
            type=decision.type,
            claim=decision.claim,
            evidence=decision.finding.finding.evidence.model_copy(
                update={"section": decision.section}
            ),
            explanation=decision.explanation,
            explanation_verified=decision.explanation_verified,
            attention=decision.attention,
            verification_status=decision.finding.verification.status,
        )
        for index, decision in enumerate(outcome.released, start=1)
    ]

    withheld = WithheldSummary(total=len(outcome.withheld))
    for item in outcome.withheld:
        status = item.verification.status
        if status is VerificationStatus.REJECTED:
            withheld.rejected += 1
        elif status is VerificationStatus.UNVERIFIED:
            withheld.unverified += 1
        elif status is VerificationStatus.PARTIALLY_VERIFIED:
            withheld.partially_verified += 1

    return AnalysisResult(
        findings=findings,
        withheld=withheld,
        proposed_count=len(verified),
        insufficient_evidence=bool(verified) and not findings,
        coverage=state.get("coverage"),
    )
