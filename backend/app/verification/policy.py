"""The output safety policy - the one place that decides what a user sees.

Phase 14 found that claim-level verification guarded Q&A and not the analysis
findings path. The fix was correct and the lesson was bigger than the fix: the
application had no single place where "may this reach a user" was decided, so
a check could protect one surface and silently miss another.

Phase 15 found the same class of defect one level down, in the *payload*
rather than the path. A finding that passes every Phase 14 check still carries
four other fields, and none of them was verified:

    section      the model's citation. Measured: "Section 99.4 (Unrestricted
                 Disclosure Permitted)" was released against a document that
                 has no section 99, under a green verified badge.
    explanation  the model's prose. Measured: an explanation reading "the
                 Employee is free to share the information with anyone" was
                 released beneath a verbatim-correct claim that the Employee
                 must NOT disclose it.
    attention    a risk level the model chose. `info` on a confidentiality
                 prohibition. Nothing derived or checked it.
    type         free-form model text, rendered as the card's heading.

So this module is not another checker. It is the release boundary. Everything
the findings endpoint publishes comes from `release_findings`, and the Q&A gate
takes its citations from the same `confirm_section` - two typed gates because
the output types genuinely differ, over one set of primitives so they cannot
drift apart. Each field a user sees arrives here either confirmed, derived by
the application, or dropped.

Three rules it enforces, in the order they matter:

1. **Nothing the model asserts about its own output decides anything.** Not a
   verification flag, not a risk level, not a citation.
2. **A field that cannot be confirmed is dropped, not shown with a caveat.**
   Except where dropping it would misrepresent the finding, in which case the
   whole finding goes.
3. **Verification can only lower a verdict.** Nothing here promotes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.schemas.findings import (
    AttentionLevel,
    VerificationReason,
    VerificationStatus,
    VerifiedFinding,
)
from app.verification.grounding import EvidenceSource
from app.verification.numeric import NumericKind, extract_dates, extract_numbers
from app.verification.semantics import (
    OBLIGATION_PHRASES,
    PROHIBITION_PHRASES,
    ClaimStatus,
    check_answer,
    evidence_context,
    has_any,
    looks_like_injection,
    normalize,
    split_claims,
    values_in_evidence,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def confirm_section(section: str | None, page_text: str | None) -> str | None:
    """The model's section label, or None if the document does not carry it.

    A citation is the one part of a finding a reader cannot check without the
    document in front of them, which makes an invented one more damaging than
    an invented sentence: it looks like the thing that makes the rest
    trustworthy.

    Whole-label containment, deliberately. Matching on a fragment would accept
    "Section 99.4 (Unrestricted Disclosure Permitted)" against any page
    containing the word "disclosure" - which is exactly the fabrication
    measured in Phase 15.

    Dropping a real-but-unconfirmable heading (one that lives in a page header
    the extractor discarded) costs a citation and keeps the finding. That is
    the right way round.
    """
    if not section or not section.strip():
        return None
    if page_text is None:
        return None
    return section if normalize(section) in normalize(page_text) else None


# ---------------------------------------------------------------------------
# Attention
# ---------------------------------------------------------------------------

#: Clause vocabulary that carries consequences a reader should look at. A
#: closed list, and a list about *what the text says*, not about what it means
#: legally - "indemnify" is a word in the document, not a judgement about
#: whether the indemnity is onerous.
_CONSEQUENCE_TERMS = (
    "indemnify", "indemnity", "indemnification", "liable", "liability",
    "penalty", "penalties", "liquidated damages", "terminate", "termination",
    "breach", "default", "forfeit", "forfeiture", "waive", "waiver",
    "exclusive", "assign", "assignment", "confidential", "confidentiality",
    "arbitration", "jurisdiction", "governing law", "auto-renew",
    "automatically renew", "renewal",
)


def derive_attention(evidence_text: str) -> AttentionLevel:
    """How much of a reader's attention this clause's *text* asks for.

    Derived from the verified evidence, never taken from the model. The model
    used to set this field, which made it a risk level chosen by the thing the
    application exists to check - and an `info` flag on a confidentiality
    prohibition is exactly what that produces.

    What this is: a count of features the quoted text demonstrably contains -
    a prohibition, an obligation, a sum of money, a deadline, and vocabulary
    that carries consequences.

    What this is NOT, and must never be described as: a legal risk assessment.
    It says nothing about whether a clause is onerous, unusual, unenforceable
    or unfair. Those are legal conclusions and this product does not reach
    them (docs/01_PRD.md sec. 6.3).
    """
    if not evidence_text:
        return AttentionLevel.INFO

    text = normalize(evidence_text)
    tokens = extract_numbers(text)

    signals = sum(
        (
            has_any(text, PROHIBITION_PHRASES),
            has_any(text, OBLIGATION_PHRASES),
            any(token.kind is NumericKind.CURRENCY for token in tokens),
            any(token.kind is NumericKind.DURATION for token in tokens)
            or bool(extract_dates(text)),
            has_any(text, _CONSEQUENCE_TERMS),
        )
    )

    # A prohibition attached to money or a deadline is the shape a reader most
    # often needs to see, so it reaches `high` without needing a fifth signal.
    money_or_deadline = any(
        token.kind in {NumericKind.CURRENCY, NumericKind.DURATION} for token in tokens
    )
    if signals >= 4 or (has_any(text, PROHIBITION_PHRASES) and money_or_deadline):
        return AttentionLevel.HIGH
    if signals >= 1:
        return AttentionLevel.REVIEW
    return AttentionLevel.INFO


# ---------------------------------------------------------------------------
# Clause type
# ---------------------------------------------------------------------------

#: The longest a category label can sensibly be. Beyond this it is not a label.
MAX_TYPE_CHARS = 40

_FALLBACK_TYPE = "clause"


def safe_type(raw: str) -> str:
    """A category label the UI can render as a heading without risk.

    Free-form by design - the model picks the category, and constraining it to
    a fixed list would lose real clause kinds. Free-form is not the same as
    unchecked, though: this is model text rendered as a heading, so it is
    bounded in length and refused if it reads as an instruction rather than a
    category.
    """
    label = " ".join(str(raw or "").split())
    if not label or len(label) > MAX_TYPE_CHARS or looks_like_injection(label):
        return _FALLBACK_TYPE
    return label


# ---------------------------------------------------------------------------
# The release decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExplanationDecision:
    """What may be done with a finding's explanation."""

    text: str
    verified: bool
    reason: VerificationReason | None = None
    """Set when the explanation disqualifies the whole finding."""


def explanation_decision(explanation: str, context: str) -> ExplanationDecision:
    """Judge a finding's plain-language explanation.

    Two controls ship here, and a third was written, measured and refused. All
    three were measured on 28 explanations written for this purpose - 20 in the
    register `prompts.py` asks the model for, 8 reversing the clause they sit
    under (`tests/fixtures_explanations.py`).

    **Shipped: values must be in the evidence.** Figures and dates survive
    paraphrase, so the same binding used for claims works here. Measured: 0
    false positives on 20 legitimate explanations, and it catches the class it
    exists for - "within twelve (12) days" written under a clause that says
    forty-five.

    **Shipped: an explanation may not be an instruction.** Same check, same
    reason as everywhere else.

    **Refused: contradiction gating.** The obvious rule - reject an explanation
    that contradicts its evidence - does not work, and the measurement is worth
    recording because it is counter-intuitive. The semantic axes are calibrated
    for one-sentence restatements; an explanation is paraphrase-heavy prose
    across two or three sentences, and against it the checks are wrong in both
    directions at once:

        rule                                   false positives   attacks missed
        contradiction vs evidence                   2 / 20             5 / 8
        contradiction vs the verified claim         2 / 20             5 / 8
        reversal axes only, overlap >= 0.6          3 / 20             3 / 8
        reversal axes only, overlap >= 0.8          1 / 20             6 / 8

    No threshold is both safe and useful. Shipping any of them would withhold
    correct findings *and* leave most reversed explanations in place, which is
    the worst of both. The residual risk - an explanation that reverses the
    clause above it - is handled by presentation instead: `verified` below is
    false unless the evidence establishes every sentence, and the UI labels
    anything unverified as interpretation rather than as a fact about the
    document. That is a weaker control than verification and is recorded as
    such in `PHASE_15_REPORT.md` sec. 11.
    """
    if looks_like_injection(explanation):
        return ExplanationDecision("", False, VerificationReason.EVIDENCE_INSTRUCTION_LIKE)

    if not context:
        # Nothing to check it against. The explanation stays, unverified.
        return ExplanationDecision(explanation, False)

    for sentence in split_claims(explanation) or [explanation]:
        if not values_in_evidence(sentence, context):
            return ExplanationDecision("", False, VerificationReason.EXPLANATION_CONTRADICTED)

    verdicts = check_answer(explanation, [context])
    verified = bool(verdicts) and all(v.status is ClaimStatus.SUPPORTED for v in verdicts)
    return ExplanationDecision(explanation, verified)


@dataclass(frozen=True)
class ReleasedFinding:
    """One finding as the application is willing to publish it.

    Every field here has been confirmed, derived or dropped. Nothing is carried
    over from the model untouched except the claim and the quote, both of which
    the verifier has already checked against the document.
    """

    finding: VerifiedFinding
    claim: str
    explanation: str
    explanation_verified: bool
    """False when the explanation is interpretation the evidence does not
    establish. It is still shown, and the UI labels it as such."""

    attention: AttentionLevel
    section: str | None
    type: str


@dataclass(frozen=True)
class ReleaseOutcome:
    """What the policy decided about a whole analysis."""

    released: list[ReleasedFinding] = field(default_factory=list)
    withheld: list[VerifiedFinding] = field(default_factory=list)
    """Paired with the reason on each item's own verification result."""


def _reject(item: VerifiedFinding, reason: VerificationReason) -> VerifiedFinding:
    """Re-issue a verdict as rejected, keeping what was already established."""
    verification = item.verification
    return VerifiedFinding(
        finding=item.finding,
        verification=verification.model_copy(
            update={
                "status": VerificationStatus.REJECTED,
                "reasons": [*verification.reasons, reason],
            }
        ),
    )


def release_finding(
    item: VerifiedFinding, document: EvidenceSource
) -> ReleasedFinding | VerifiedFinding:
    """Decide whether and how one verified finding may be shown.

    Returns a `ReleasedFinding` when it may be published, or the finding with a
    rejected verdict when it may not. The caller does not get to choose.
    """
    if not item.is_displayable_as_fact:
        return item

    evidence = item.finding.evidence
    page_text = document.page_text(evidence.page) if evidence else None
    context = (
        evidence_context(evidence.quote, page_text)
        if evidence and page_text is not None
        else ""
    )

    # --- The explanation ---------------------------------------------------
    # Two controls, and both of them were chosen by measurement rather than by
    # argument. See `explanation_decision` for what was measured and what was
    # refused.
    explanation = item.finding.explanation or ""
    explanation_verified = False
    if explanation.strip():
        decision = explanation_decision(explanation, context)
        if decision.reason is not None:
            return _reject(item, decision.reason)
        explanation = decision.text
        explanation_verified = decision.verified

    return ReleasedFinding(
        finding=item,
        claim=item.finding.claim,
        explanation=explanation,
        explanation_verified=explanation_verified,
        # Derived from the verified evidence. Never the model's choice.
        attention=derive_attention(context or (evidence.quote if evidence else "")),
        section=confirm_section(evidence.section if evidence else None, page_text),
        type=safe_type(item.finding.type),
    )


def release_findings(
    verified: list[VerifiedFinding], document: EvidenceSource
) -> ReleaseOutcome:
    """The release boundary for the analysis path.

    Everything the findings endpoint publishes comes from here. A finding that
    is not in `released` is not shown, whatever else is true about it.
    """
    outcome = ReleaseOutcome()
    dropped_sections = 0
    unverified_explanations = 0

    for item in verified:
        decision = release_finding(item, document)
        if isinstance(decision, ReleasedFinding):
            outcome.released.append(decision)
            if decision.finding.finding.evidence and (
                decision.finding.finding.evidence.section and decision.section is None
            ):
                dropped_sections += 1
            if decision.explanation and not decision.explanation_verified:
                unverified_explanations += 1
        else:
            outcome.withheld.append(decision)

    # Metadata only - no claims, quotes, explanations or citations.
    logger.info(
        "output policy applied released=%d withheld=%d citations_dropped=%d "
        "explanations_unverified=%d",
        len(outcome.released),
        len(outcome.withheld),
        dropped_sections,
        unverified_explanations,
    )
    return outcome
