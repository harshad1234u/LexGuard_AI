"""Schemas for model-proposed findings and their verification result.

Nothing here mentions Nemotron, NVIDIA or LangChain. A finding is whatever some
model proposed; the verifier judges it the same way regardless of origin, so a
different provider can be swapped in without touching verification
(docs/02_ARCHITECTURE.md sec. 7).

A `Finding` is a PROPOSAL. A `VerifiedFinding` is what the application is
willing to stand behind, and only `VerificationStatus.VERIFIED` may be shown to
a user as an established fact about the document.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AttentionLevel(StrEnum):
    """How much the reader should look at this clause.

    Not a legal conclusion (docs/01_PRD.md sec. 6.3) - a prompt to read.
    """

    INFO = "info"
    REVIEW = "review"
    HIGH = "high"


class LanguageCode(StrEnum):
    """Languages a reader may ask for (Phase 23).

    The document's own language is detected by the application
    (`app.documents.language`), never taken from the model.
    """

    EN = "en"
    TA = "ta"


#: Upper bound on a model-supplied translation. Translations are extra text
#: shown under a label, so an oversized one is refused rather than truncated.
MAX_TRANSLATION_CHARS = 2000


class FindingKind(StrEnum):
    """What sort of statement the model says it is making. Recorded, not trusted."""

    EXTRACTION = "extraction"
    INTERPRETATION = "interpretation"
    INFERENCE = "inference"


class Evidence(BaseModel):
    """Where in the document a claim is said to come from."""

    page: int = Field(description="1-based page number as cited by the model.")
    quote: str = Field(default="", description="Text the model says appears on that page.")
    section: str | None = None


class Finding(BaseModel):
    """One model-proposed observation about the document. Untrusted until verified."""

    id: str | None = None
    type: str = Field(description="Clause category, e.g. 'termination'. Free-form by design.")
    claim: str
    evidence: Evidence | None = None
    explanation: str = ""
    attention: AttentionLevel = AttentionLevel.INFO
    kind: FindingKind | None = None
    explanation_translation: str = Field(
        default="",
        max_length=MAX_TRANSLATION_CHARS,
        description=(
            "The explanation in the reader's requested language, when one was asked for. "
            "Never checked semantically; released only under the conditions in "
            "`app.verification.policy.translation_decision`."
        ),
    )


class ModelAnalysis(BaseModel):
    """A model's complete proposal for a document."""

    findings: list[Finding] = Field(default_factory=list)


class ModelAnswer(BaseModel):
    """A model's proposed answer to a document-grounded question.

    Like a Finding, this is a proposal: `evidence` goes to the verifier before
    any of it is shown as fact. `not_found` is the model declining to guess,
    which is the required behaviour when the document is silent
    (docs/04_SECURITY_GROUNDING.md sec. 7).
    """

    answer: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    not_found: bool = False
    answer_translation: str = Field(default="", max_length=MAX_TRANSLATION_CHARS)
    """The answer in the reader's requested language. The checked answer is
    `answer`; this is released only when every sentence of `answer` survived."""


class VerificationStatus(StrEnum):
    """Outcome of deterministic verification (docs/04_SECURITY_GROUNDING.md sec. 5)."""

    VERIFIED = "verified"
    """Evidence exists in the document and every deterministic check passed."""

    PARTIALLY_VERIFIED = "partially_verified"
    """The quote was found, but one non-critical check could not be settled -
    an ambiguous date, typically. Not presentable as an established fact."""

    REJECTED = "rejected"
    """The evidence contradicts the document, or does not exist in it."""

    UNVERIFIED = "unverified"
    """Not enough was supplied, or available, to decide either way."""


class VerificationReason(StrEnum):
    """Why a finding was not verified. Machine-readable for the UI and logs."""

    MISSING_EVIDENCE = "missing_evidence"
    EMPTY_QUOTE = "empty_quote"
    QUOTE_TOO_LONG = "quote_too_long"
    INVALID_PAGE = "invalid_page"
    PAGE_NOT_EXTRACTED = "page_not_extracted"
    QUOTE_NOT_FOUND = "quote_not_found"
    NUMERIC_MISMATCH = "numeric_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    DATE_MISMATCH = "date_mismatch"
    DATE_AMBIGUOUS = "date_ambiguous"

    # --- Claim-level semantic verification (Phase 14) ---------------------
    # A quote can be real, on the right page, with every figure agreeing, and
    # the sentence the model built on it can still say the opposite. These
    # three reasons carry that verdict for the analysis path, which until
    # Phase 14 checked the evidence and never the claim resting on it.
    CLAIM_CONTRADICTED = "claim_contradicted"
    CLAIM_UNSUPPORTED = "claim_unsupported"
    EVIDENCE_INSTRUCTION_LIKE = "evidence_instruction_like"

    # --- Output policy (Phase 15) ------------------------------------------
    # A finding is more than its claim. An explanation that reverses the clause
    # it sits under is the model having misread the document, and it reaches a
    # reader in larger type than the quote does.
    EXPLANATION_CONTRADICTED = "explanation_contradicted"


#: Plain-language explanations, safe to show a non-technical reader.
REASON_MESSAGES: dict[VerificationReason, str] = {
    VerificationReason.MISSING_EVIDENCE: "This statement was not accompanied by any evidence from the document.",
    VerificationReason.EMPTY_QUOTE: "No quoted text was supplied for this statement.",
    VerificationReason.QUOTE_TOO_LONG: "The quoted passage was too long to verify reliably.",
    VerificationReason.INVALID_PAGE: "The cited page does not exist in this document.",
    VerificationReason.PAGE_NOT_EXTRACTED: "The cited page's text was never captured, so this could not be checked.",
    VerificationReason.QUOTE_NOT_FOUND: "The quoted text was not found on the cited page.",
    VerificationReason.NUMERIC_MISMATCH: "A number in this statement does not match the document.",
    VerificationReason.CURRENCY_MISMATCH: "An amount in this statement does not match the document.",
    VerificationReason.DATE_MISMATCH: "A date in this statement does not match the document.",
    VerificationReason.DATE_AMBIGUOUS: "A date could not be read unambiguously, so it was not confirmed.",
    VerificationReason.CLAIM_CONTRADICTED: "The quoted text says something materially different from this statement.",
    VerificationReason.CLAIM_UNSUPPORTED: "The quoted text does not establish what this statement says.",
    VerificationReason.EVIDENCE_INSTRUCTION_LIKE: (
        "The quoted text is an instruction addressed to this assistant rather than a "
        "provision of the agreement, so it cannot support a statement about the document."
    ),
    VerificationReason.EXPLANATION_CONTRADICTED: (
        "The plain-language explanation says the opposite of the text it explains."
    ),
}


class QuoteMatchType(StrEnum):
    EXACT = "exact"
    """Present verbatim once formatting differences are normalised away."""

    NEAR = "near"
    """Found with minor differences, and every value in it confirmed present."""

    NONE = "none"


class VerificationResult(BaseModel):
    """The deterministic verdict on one finding.

    The individual checks are reported alongside the status so a reader can see
    which part failed rather than being handed an opaque rejection.
    """

    status: VerificationStatus
    page_match: bool = False
    quote_match: bool = False
    numeric_match: bool = False
    date_match: bool = False
    quote_match_type: QuoteMatchType = QuoteMatchType.NONE
    reasons: list[VerificationReason] = Field(default_factory=list)

    @property
    def is_displayable_as_fact(self) -> bool:
        """The grounding invariant, in one place.

        Only VERIFIED may be presented to the user as an established fact about
        the document. Everything else - including PARTIALLY_VERIFIED - must be
        labelled or withheld (docs/04_SECURITY_GROUNDING.md sec. 11).
        """
        return self.status is VerificationStatus.VERIFIED

    @property
    def explanation(self) -> str:
        if self.status is VerificationStatus.VERIFIED:
            return "This statement is supported by the document."
        if not self.reasons:
            return "This statement could not be confirmed against the document."
        return " ".join(REASON_MESSAGES[reason] for reason in self.reasons)


class VerifiedFinding(BaseModel):
    """A proposal paired with the application's verdict on it."""

    finding: Finding
    verification: VerificationResult

    @property
    def is_displayable_as_fact(self) -> bool:
        return self.verification.is_displayable_as_fact
