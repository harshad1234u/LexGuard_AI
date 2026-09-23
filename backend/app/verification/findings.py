"""Claim-level verification for the analysis path.

Phase 10 established that a verified quote does not verify the prose built on
it, and closed that gap - for question answering only. The analysis path,
which is the product's primary surface, kept running evidence checks alone:
`verify_analysis` asked whether the quote existed on the cited page and
whether the figures agreed, and nothing asked whether the model's sentence
meant what the quote meant.

Phase 14 measured what that cost. Against the document

    "The Employee must not disclose Confidential Information to any third party."

a finding whose claim read

    "The Employee may disclose Confidential Information to any third party."

was returned as `verified`, with the reversed sentence shown under a green
"Verified against uploaded document" badge and the quote that contradicts it
printed underneath. The same held for a finding quoting an injected
instruction: the sentence really is in the file, so every evidence check
passed.

This module closes both, by running the checks the Q&A gate already runs. No
new rule is invented here and no vocabulary is duplicated - `looks_like_
injection` and `check_answer` are the same implementations the Q&A path uses,
so the two surfaces cannot drift apart.

Direction of travel: this can only lower a verdict. A finding the evidence
checks refused is never promoted, and a claim that cannot be judged is
withheld rather than released.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.findings import (
    ModelAnalysis,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
    VerifiedFinding,
)
from app.verification.grounding import EvidenceSource, all_text, verify_analysis
from app.verification.semantics import (
    ClaimStatus,
    ClaimVerdict,
    check_answer,
    check_claim,
    conflicting_definitions,
    defines_a_contested_term,
    evidence_context,
    looks_like_injection,
    quotes_reported_speech,
)

logger = get_logger(__name__)

#: Verdicts worth checking further. A finding already rejected or unverified is
#: withheld whatever the semantics say, and re-judging it could only produce a
#: misleading second reason.
_CHECKABLE = frozenset(
    {VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED}
)


def _claim_verdicts(claim: str, context: str) -> list[ClaimVerdict]:
    """Judge a finding's claim against its evidence sentence.

    `check_answer` splits on sentences and drops fragments too short to assert
    anything. A finding's claim is one sentence by the prompt's contract, and a
    short one ("Rent is $2,400 per month.") falls below that floor - so an
    empty split is judged whole rather than treated as making no claim at all,
    which would have released it unchecked.
    """
    verdicts = check_answer(claim, [context])
    return verdicts or [check_claim(claim, context)]


def _downgrade(
    item: VerifiedFinding,
    status: VerificationStatus,
    reason: VerificationReason,
) -> VerifiedFinding:
    """Re-issue a verdict at a lower status, keeping what was already decided.

    The evidence-level results (`page_match`, `quote_match`, ...) are preserved:
    a reader is owed the fact that the quote was found, alongside the reason
    the statement built on it was still not shown.
    """
    verification = item.verification
    return VerifiedFinding(
        finding=item.finding,
        verification=VerificationResult(
            status=status,
            page_match=verification.page_match,
            quote_match=verification.quote_match,
            numeric_match=verification.numeric_match,
            date_match=verification.date_match,
            quote_match_type=verification.quote_match_type,
            reasons=[*verification.reasons, reason],
        ),
    )


def check_finding(
    item: VerifiedFinding,
    document: EvidenceSource,
    contested: set[str] | None = None,
) -> VerifiedFinding:
    """Verify that a finding's claim says what its evidence says.

    Fail-closed at every step: no evidence, no page text, or no usable context
    all mean the claim cannot be checked, and an unchecked claim is not shown.
    """
    if item.verification.status not in _CHECKABLE:
        return item

    evidence = item.finding.evidence
    if evidence is None:
        return _downgrade(
            item, VerificationStatus.UNVERIFIED, VerificationReason.MISSING_EVIDENCE
        )

    page_text = document.page_text(evidence.page)
    if page_text is None:
        return _downgrade(
            item, VerificationStatus.UNVERIFIED, VerificationReason.PAGE_NOT_EXTRACTED
        )

    # A quote that addresses the assistant is not a provision of the agreement,
    # however genuinely it appears in the file. Both the quote and the sentence
    # around it are tested, because a model can quote the payload and leave the
    # instruction that introduced it just outside the quotation marks.
    context = evidence_context(evidence.quote, page_text)
    if (
        looks_like_injection(evidence.quote)
        or looks_like_injection(context)
        or quotes_reported_speech(context, evidence.quote)
        or defines_a_contested_term(context, contested or set())
    ):
        return _downgrade(
            item,
            VerificationStatus.REJECTED,
            VerificationReason.EVIDENCE_INSTRUCTION_LIKE,
        )

    if not context:
        return _downgrade(
            item, VerificationStatus.UNVERIFIED, VerificationReason.CLAIM_UNSUPPORTED
        )

    verdicts = _claim_verdicts(item.finding.claim, context)
    if any(verdict.status is ClaimStatus.CONTRADICTED for verdict in verdicts):
        # The model misread the clause it quoted. That is a stronger statement
        # than "not established", and the status says so.
        return _downgrade(
            item, VerificationStatus.REJECTED, VerificationReason.CLAIM_CONTRADICTED
        )
    if any(verdict.status is not ClaimStatus.SUPPORTED for verdict in verdicts):
        # Every sentence of the claim must hold. A finding is displayed whole,
        # so partial support is not something the reader could act on safely.
        return _downgrade(
            item, VerificationStatus.UNVERIFIED, VerificationReason.CLAIM_UNSUPPORTED
        )

    return item


def verify_analysis_claims(
    analysis: ModelAnalysis, document: EvidenceSource
) -> list[VerifiedFinding]:
    """Verify every finding's evidence and then the claim resting on it.

    The single entry point the workflow calls. `verify_analysis` is left
    unchanged and still used directly by the Q&A path's sibling, so the
    evidence layer keeps exactly one implementation.
    """
    # Computed once for the document rather than per finding: a term defined
    # twice and differently is a fact about the file, not about one clause.
    contested = conflicting_definitions(all_text(document))
    results = [
        check_finding(item, document, contested)
        for item in verify_analysis(analysis, document)
    ]

    # Metadata only - claims and quotes are document content and are not logged.
    counts: dict[str, int] = {}
    for item in results:
        for reason in item.verification.reasons:
            if reason in _SEMANTIC_REASONS:
                counts[str(reason)] = counts.get(str(reason), 0) + 1
    if counts:
        logger.warning("findings withheld by claim verification outcomes=%s", counts)

    return results


_SEMANTIC_REASONS = frozenset(
    {
        VerificationReason.CLAIM_CONTRADICTED,
        VerificationReason.CLAIM_UNSUPPORTED,
        VerificationReason.EVIDENCE_INSTRUCTION_LIKE,
    }
)
