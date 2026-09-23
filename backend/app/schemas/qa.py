"""Schemas for document-grounded question answering.

A question is answered from one uploaded document and nothing else. What the
model proposes is a `ModelAnswer`; what a client receives is an `AskResponse`,
which is what survived deterministic verification and the Q&A safety gate.

The distinction the whole contract rests on:

    answer          - the model's interpretation, released only when the
                      document was shown to support it
    evidence        - quotes the verifier located in the document
    status          - the application's verdict on how well supported the
                      answer is, never the model's own claim about itself
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.schemas.findings import VerificationStatus

#: Maximum question length. Generous for a real question, small enough that a
#: pasted document cannot be smuggled in as one.
MAX_QUESTION_CHARS = 2000

#: Shown with every answer (docs/01_PRD.md sec. 12).
DISCLAIMER = (
    "This is legal information drawn from your uploaded document, not legal advice. "
    "Check anything that matters against the document itself and with a qualified lawyer."
)

#: What the application says when it cannot stand behind an answer. Deliberately
#: about the *evidence*, not about the document's contents: the system is not in
#: a position to say a clause does not exist (docs/04_SECURITY_GROUNDING.md sec. 7).
NOT_FOUND_ANSWER = (
    "I couldn't find this information in the uploaded document. "
    "That does not mean the document is silent on it - only that nothing could be "
    "confirmed, so nothing is shown."
)


class AnswerStatus(StrEnum):
    """How well the document supports the answer being returned.

    A support level, not a confidence score. The project has no calibrated
    basis for a probability and will not imply one (docs/09_DECISIONS.md).

    Coverage refusals and provider failures are *not* values here. They are
    HTTP error responses carrying the project's standard error envelope, the
    same as everywhere else in this API - see docs/07_API_SPEC.md.
    """

    SUPPORTED = "supported"
    """At least one piece of evidence verified, and none was contradicted."""

    PARTIALLY_SUPPORTED = "partially_supported"
    """Some support was found, but not all of it held up. Read the evidence."""

    NOT_FOUND = "not_found"
    """Nothing in the document could be confirmed to answer this. The model's
    own words are withheld rather than shown unsupported."""


class AnswerEvidence(BaseModel):
    """One quote the application located in the document.

    Only evidence the verifier could place in the document appears here.
    Rejected evidence - a fabricated quote, an invented page - is counted and
    dropped, never shown (docs/04_SECURITY_GROUNDING.md sec. 11).
    """

    quote: str = Field(description="Text as the document writes it.")
    page: int
    section: str | None = None
    verification_status: VerificationStatus = Field(
        description="The application's verdict. Never the model's claim about itself."
    )
    note: str = Field(
        default="",
        description="Plain-language caveat, present when the status is not `verified`.",
    )


class AskRequest(BaseModel):
    """Request body for POST /api/v1/documents/{document_id}/ask."""

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_CHARS,
        description="A question about this document. Treated as untrusted input.",
    )

    @field_validator("question")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """A question of only whitespace is not a question.

        `min_length` alone would accept "   ", which reaches the model as an
        empty instruction and invites it to invent something to answer.
        """
        if not value.strip():
            raise ValueError("The question cannot be empty.")
        return value


class AskResponse(BaseModel):
    """Response body for POST /api/v1/documents/{document_id}/ask."""

    document_id: str
    question: str = Field(description="Echoed back so a client can pair answer with question.")
    answer: str = Field(
        description=(
            "The model's answer when the document supported it, otherwise the "
            "application's own not-found text. Never the model's unsupported words."
        )
    )
    status: AnswerStatus
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    withheld_evidence: int = Field(
        default=0,
        description=(
            "How many proposed quotes the verifier could not place in the document. "
            "Counted so their absence is visible; their text is never returned."
        ),
    )
    claims_checked: int = Field(
        default=0,
        description="Statements the answer made, each checked against its evidence separately.",
    )
    claims_withheld: int = Field(
        default=0,
        description=(
            "Statements dropped from the answer because the evidence did not establish them. "
            "Their text is never returned."
        ),
    )
    disclaimer: str = DISCLAIMER
