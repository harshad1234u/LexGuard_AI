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

import asyncio
import re
import time

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
from app.models.reasoning import (
    ModelReasoning,
    ReasoningFindingInput,
    ReasoningNote,
    ReasoningProvider,
    ReasoningRequest,
)
from app.models.transport import ProviderFailureKind, failure_kind
from app.schemas.analysis import (
    AnalysisResult,
    AnalysisStage,
    CoverageSummary,
    ErrorCategory,
    ReasoningNoteOut,
    ReasoningResult,
    ReasoningStatus,
    VerifiedFindingOut,
    WithheldSummary,
)
from app.schemas.findings import LanguageCode, ModelAnalysis, VerificationStatus
from app.schemas.provenance import Provenance
from app.agents.state import AnalysisState, fail
from app.verification.coverage import CoverageGateError, require_complete_coverage
from app.verification.findings import verify_analysis_claims
from app.verification.policy import (
    VERIFICATION_POLICY_VERSION,
    ReleasedFinding,
    release_findings,
)
from app.verification.semantics import looks_like_injection, values_in_evidence

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
        analysis = await provider.analyze_document(
            AnalysisRequest(payload=payload, language=state.get("language", LanguageCode.EN))
        )
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
        return {
            **update,
            **fail(state, category, exc.message),
            "provider_failure_kind": str(failure_kind(exc)),
        }
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
        outcome = release_findings(
            verified, _record(state), state.get("language", LanguageCode.EN)
        )
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

    language = state.get("language", LanguageCode.EN)
    findings = [
        VerifiedFindingOut(
            id=released_id(decision, index),
            type=decision.type,
            claim=decision.claim,
            evidence=decision.finding.finding.evidence.model_copy(
                update={"section": decision.section}
            ),
            explanation=decision.explanation,
            explanation_verified=decision.explanation_verified,
            attention=decision.attention,
            verification_status=decision.finding.verification.status,
            explanation_translation=decision.explanation_translation,
            explanation_translation_language=(
                LanguageCode(language) if decision.explanation_translation else None
            ),
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
        language=language,
        provenance=_provenance(state),
        reasoning=_reasoning_result(state),
    )


def released_id(decision: ReleasedFinding, index: int) -> str:
    """The id a released finding is published under.

    One rule, used by both `build_result` and the reasoning stage, so a note's
    `finding_ids` always refer to ids a client can actually see.
    """
    return decision.finding.finding.id or f"f_{index:03d}"


def _provenance(state: AnalysisState) -> Provenance | None:
    if not state.get("provider_name"):
        return None
    reasoning_ran = state.get("reasoning_status") not in (None, ReasoningStatus.DISABLED)
    return Provenance(
        provider=state["provider_name"],
        model=state.get("provider_model", "unknown"),
        reasoning_provider=state.get("reasoning_provider_name") if reasoning_ran else None,
        reasoning_model=state.get("reasoning_provider_model") if reasoning_ran else None,
        verification_policy_version=VERIFICATION_POLICY_VERSION,
        status="completed",
    )


def _reasoning_result(state: AnalysisState) -> ReasoningResult | None:
    status = state.get("reasoning_status")
    if status is None:
        return None
    return ReasoningResult(
        status=status,
        failure_kind=state.get("reasoning_failure_kind"),
        provider=state.get("reasoning_provider_name"),
        notes=list(state.get("reasoning_notes", [])),
        withheld_count=state.get("reasoning_withheld", 0),
    )


# --- 8. reasoning (Phase 23) -----------------------------------------------------
#
# Runs only after the output gate has decided, over what it released. Neither
# node below reads `model_analysis` or `verified_findings`, writes
# `release_outcome`, or calls `fail()`: a reasoning failure is recorded on the
# reasoning block and the analysis completes with its findings untouched.

#: Below this much remaining analysis budget, reasoning is skipped rather than
#: risk pushing a finished analysis into the whole-run timeout.
MIN_REASONING_SECONDS = 10

#: Notes may not assert legal conclusions or claim verification. Deterministic,
#: deliberately narrow, and a refusal rather than an edit.
_CONCLUSION_TERMS = re.compile(
    r"\b(verified|unenforceable|enforceable|legally binding|guarantee[sd]?|"
    r"you should sign|you should not sign)\b",
    re.IGNORECASE,
)


def _reasoning_update(status: ReasoningStatus, **extra) -> AnalysisState:
    return {"reasoning_status": status, **extra}


async def reason_node(
    state: AnalysisState, reasoning_provider: ReasoningProvider | None = None
) -> AnalysisState:
    """Ask the reasoning provider about the RELEASED findings only."""
    if reasoning_provider is None:
        return _reasoning_update(ReasoningStatus.DISABLED)

    identity = {
        "reasoning_provider_name": str(getattr(reasoning_provider, "name", "unknown")),
        "reasoning_provider_model": str(getattr(reasoning_provider, "model_id", "") or "unknown"),
    }
    outcome = state.get("release_outcome")
    released = list(outcome.released) if outcome is not None else []

    if len(released) < 2:
        return _reasoning_update(ReasoningStatus.SKIPPED, **identity)

    if not reasoning_provider.is_configured:
        return _reasoning_update(
            ReasoningStatus.UNAVAILABLE,
            reasoning_failure_kind=str(ProviderFailureKind.CONFIGURATION),
            **identity,
        )

    deadline = state.get("deadline")
    if deadline is not None and deadline - time.monotonic() < MIN_REASONING_SECONDS:
        _log(state, "reasoning_skipped", reason="insufficient_time")
        return _reasoning_update(ReasoningStatus.SKIPPED, **identity)

    inputs = tuple(
        ReasoningFindingInput(
            id=released_id(decision, index),
            type=decision.type,
            claim=decision.claim,
            quote=decision.finding.finding.evidence.quote,
            page=decision.finding.finding.evidence.page,
        )
        for index, decision in enumerate(released, start=1)
        if decision.finding.finding.evidence is not None
    )
    if len(inputs) < 2:
        return _reasoning_update(ReasoningStatus.SKIPPED, **identity)

    # Never outlive the whole-run budget: a reasoning call that did would turn
    # a completed analysis into a timed-out one and lose its findings.
    budget = None
    if deadline is not None:
        budget = max(1.0, deadline - time.monotonic() - 1.0)

    try:
        proposal = await asyncio.wait_for(
            reasoning_provider.reason_about_findings(
                ReasoningRequest(document_id=state["document_id"], findings=list(inputs))
            ),
            timeout=budget,
        )
    except TimeoutError:
        _log(state, "reasoning_failed", kind="timeout")
        return _reasoning_update(
            ReasoningStatus.FAILED,
            reasoning_failure_kind=str(ProviderFailureKind.TIMEOUT),
            **identity,
        )
    except ModelError as exc:
        kind = failure_kind(exc)
        _log(state, "reasoning_failed", kind=str(kind))
        status = (
            ReasoningStatus.UNAVAILABLE
            if kind is ProviderFailureKind.CONFIGURATION
            else ReasoningStatus.FAILED
        )
        return _reasoning_update(status, reasoning_failure_kind=str(kind), **identity)
    except Exception as exc:
        _log(state, "reasoning_failed", kind="unknown", reason=type(exc).__name__)
        return _reasoning_update(
            ReasoningStatus.FAILED,
            reasoning_failure_kind=str(ProviderFailureKind.UNKNOWN),
            **identity,
        )

    _log(state, "reasoning_responded", proposed=len(proposal.notes))
    return _reasoning_update(
        ReasoningStatus.COMPLETED,
        reasoning_input=inputs,
        reasoning_proposal=proposal,
        **identity,
    )


def _squash(text: str) -> str:
    return " ".join(text.split())


def gate_note(
    note: ReasoningNote, inputs: dict[str, ReasoningFindingInput]
) -> tuple[bool, bool]:
    """(releasable, evidence_checked) for one proposed note.

    Refused when it cites an id it was not shown, quotes anything that is not
    text from a finding it cites, carries an instruction, asserts a legal
    conclusion or verification, or states a figure its cited quotes do not
    contain. A released note is still only interpretation: `evidence_checked`
    says the quotes are real, not that the note is right.
    """
    if any(finding_id not in inputs for finding_id in note.finding_ids):
        return False, False
    cited = [inputs[finding_id].quote for finding_id in note.finding_ids]
    cited_text = " ".join(cited)

    if looks_like_injection(note.text) or _CONCLUSION_TERMS.search(note.text):
        return False, False
    if not values_in_evidence(note.text, cited_text):
        return False, False

    for quote in note.quotes:
        squashed = _squash(quote)
        if not squashed or looks_like_injection(quote):
            return False, False
        if not any(squashed in _squash(source) for source in cited):
            return False, False

    return True, bool(note.quotes)


def reason_gate_node(state: AnalysisState) -> AnalysisState:
    """Release only notes that stay inside what the provider was shown."""
    if state.get("reasoning_status") is not ReasoningStatus.COMPLETED:
        return {}

    proposal: ModelReasoning = state.get("reasoning_proposal") or ModelReasoning()
    inputs = {item.id: item for item in state.get("reasoning_input", ())}

    notes: list[ReasoningNoteOut] = []
    withheld = 0
    for note in proposal.notes:
        releasable, checked = gate_note(note, inputs)
        if not releasable:
            withheld += 1
            continue
        notes.append(
            ReasoningNoteOut(
                id=f"n_{len(notes) + 1:03d}",
                category=str(note.category),
                text=note.text.strip(),
                finding_ids=list(note.finding_ids),
                quotes=[quote.strip() for quote in note.quotes],
                evidence_checked=checked,
            )
        )

    _log(state, "reasoning_gated", released=len(notes), withheld=withheld)
    return {"reasoning_notes": notes, "reasoning_withheld": withheld}
