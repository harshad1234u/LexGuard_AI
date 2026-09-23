"""Phase 9: verification and the safety gate for document-grounded answers.

    fake model -> REAL Phase 5 verifier -> REAL Q&A gate

The verifier is never mocked. A fake model supplies the answers a real one
might give - including dishonest ones - and the deterministic machinery decides
what a user is allowed to see.

No test here reaches NVIDIA.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import ModelAnswer, VerificationStatus
from app.schemas.qa import NOT_FOUND_ANSWER, AnswerStatus, AskRequest
from app.verification.qa import gate_answer, verify_answer

PAGE_ONE = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
    "3. Fees. The Client shall pay GBP 5,000 per month.\n"
)
PAGE_TWO = (
    "7. Confidentiality. Each party shall keep the other's information confidential "
    "for five years after termination.\n"
)


class FakeDocument:
    """A document the verifier can read, with nothing else attached."""

    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


@pytest.fixture
def document() -> FakeDocument:
    return FakeDocument({1: PAGE_ONE, 2: PAGE_TWO})


def answer_of(text: str, evidence: list[dict] | None = None, not_found: bool = False):
    return ModelAnswer.model_validate(
        {"answer": text, "evidence": evidence or [], "not_found": not_found}
    )


def gate(document, answer, question: str = "What is the notice period?"):
    return gate_answer(
        document_id="doc_test",
        question=question,
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )


# --- Supported answers --------------------------------------------------------
class TestSupportedAnswers:
    def test_a_grounded_answer_is_released_with_its_evidence(self, document):
        response = gate(
            document,
            answer_of(
                "Either party may terminate with 30 days' written notice.",
                [{"page": 1, "quote": "30 days' written notice"}],
            ),
        )

        assert response.status is AnswerStatus.SUPPORTED
        assert "30 days" in response.answer
        assert len(response.evidence) == 1
        assert response.evidence[0].page == 1
        assert response.evidence[0].verification_status is VerificationStatus.VERIFIED
        assert response.evidence[0].note == ""
        assert response.withheld_evidence == 0

    def test_evidence_from_a_later_page_verifies(self, document):
        response = gate(
            document,
            answer_of(
                "Confidentiality lasts five years after termination.",
                [{"page": 2, "quote": "confidential for five years after termination"}],
            ),
            question="How long does confidentiality last?",
        )

        assert response.status is AnswerStatus.SUPPORTED
        assert response.evidence[0].page == 2

    def test_a_currency_amount_is_checked_against_the_document(self, document):
        response = gate(
            document,
            answer_of(
                "The Client pays GBP 5,000 per month.",
                [{"page": 1, "quote": "The Client shall pay GBP 5,000 per month"}],
            ),
            question="What are the fees?",
        )

        assert response.status is AnswerStatus.SUPPORTED

    def test_every_answer_carries_the_disclaimer(self, document):
        response = gate(
            document,
            answer_of("...", [{"page": 1, "quote": "30 days' written notice"}]),
        )
        assert "not legal advice" in response.disclaimer


# --- Fabrication is caught ------------------------------------------------------
class TestFabricatedEvidence:
    def test_an_invented_page_number_is_rejected(self, document):
        response = gate(
            document,
            answer_of(
                "Termination requires 30 days' notice.",
                [{"page": 99, "quote": "30 days' written notice"}],
            ),
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert response.answer == NOT_FOUND_ANSWER
        assert response.evidence == []
        assert response.withheld_evidence == 1

    def test_a_fabricated_quote_is_rejected(self, document):
        response = gate(
            document,
            answer_of(
                "The agreement may be terminated immediately for convenience.",
                [{"page": 1, "quote": "may be terminated immediately for convenience"}],
            ),
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert response.evidence == []

    def test_a_wrong_number_in_the_answer_is_rejected(self, document):
        """The quote is real; the answer built on it misstates the value."""
        response = gate(
            document,
            answer_of(
                "Either party may terminate with 60 days' written notice.",
                [{"page": 1, "quote": "30 days' written notice"}],
            ),
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert "60 days" not in response.answer

    def test_a_wrong_currency_amount_is_rejected(self, document):
        response = gate(
            document,
            answer_of(
                "The Client shall pay GBP 8,000 per month.",
                [{"page": 1, "quote": "The Client shall pay GBP 5,000 per month"}],
            ),
            question="What are the fees?",
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert "8,000" not in response.answer

    def test_a_reversed_clause_is_rejected(self, document):
        """Dropping a 'not' is a tiny edit and a total reversal."""
        response = gate(
            document,
            answer_of(
                "Neither party may terminate this agreement.",
                [{"page": 1, "quote": "Either party may not terminate this agreement"}],
            ),
        )

        assert response.status is AnswerStatus.NOT_FOUND

    def test_a_quote_from_an_unextracted_page_cannot_verify(self):
        document = FakeDocument({1: PAGE_ONE, 2: None})
        response = gate(
            document,
            answer_of("Confidentiality lasts five years.", [{"page": 2, "quote": "five years"}]),
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert response.withheld_evidence == 1

    def test_evidence_cannot_come_from_another_document(self, document):
        """A quote is only ever matched against the document that was asked about."""
        other_document_text = "12. Arbitration. Disputes go to arbitration in Singapore."
        response = gate(
            document,
            answer_of(
                "Disputes are arbitrated in Singapore.",
                [{"page": 1, "quote": other_document_text}],
            ),
            question="How are disputes resolved?",
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert "Singapore" not in response.answer
        assert "Singapore" not in str(response.evidence)


# --- Not found ---------------------------------------------------------------------
class TestNotFound:
    def test_the_model_declining_is_honoured(self, document):
        response = gate(
            document,
            answer_of("The document does not mention this.", not_found=True),
            question="What is the governing law?",
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert response.answer == NOT_FOUND_ANSWER

    def test_an_answer_with_no_evidence_is_not_released(self, document):
        """A confident answer with nothing behind it is the failure mode."""
        response = gate(
            document,
            answer_of("The governing law is the law of England and Wales.", []),
            question="What is the governing law?",
        )

        assert response.status is AnswerStatus.NOT_FOUND
        assert "England" not in response.answer

    def test_not_found_never_claims_the_clause_is_absent(self, document):
        response = gate(document, answer_of("No.", not_found=True))

        # It says the information could not be confirmed, not that the
        # document lacks the clause.
        assert "does not mean the document is silent" in response.answer

    def test_a_model_claiming_support_it_lacks_gets_no_credit(self, document):
        """`not_found: false` is not evidence of anything."""
        response = gate(
            document,
            answer_of("Yes, absolutely, clause 9 covers this.", [], not_found=False),
        )
        assert response.status is AnswerStatus.NOT_FOUND


# --- Mixed support -------------------------------------------------------------------
class TestPartialSupport:
    def test_one_good_and_one_fabricated_quote_downgrades_the_answer(self, document):
        response = gate(
            document,
            answer_of(
                "Either party may terminate with 30 days' written notice.",
                [
                    {"page": 1, "quote": "30 days' written notice"},
                    {"page": 1, "quote": "and the deposit is forfeited"},
                ],
            ),
        )

        assert response.status is AnswerStatus.PARTIALLY_SUPPORTED
        assert len(response.evidence) == 1
        assert response.withheld_evidence == 1
        assert "deposit" not in str(response.evidence)

    def test_withheld_evidence_text_is_never_returned(self, document):
        response = gate(
            document,
            answer_of(
                "Either party may terminate with 30 days' written notice.",
                [
                    {"page": 1, "quote": "30 days' written notice"},
                    {"page": 42, "quote": "a completely invented clause about penalties"},
                ],
            ),
        )

        assert "invented clause" not in str(response.model_dump())
        assert response.withheld_evidence == 1


# --- Question validation --------------------------------------------------------------
class TestQuestionValidation:
    @pytest.mark.parametrize("bad", ["", "   ", "\n\t  \n"])
    def test_blank_questions_are_refused(self, bad):
        with pytest.raises(ValueError):
            AskRequest(question=bad)

    def test_an_overlong_question_is_refused(self):
        with pytest.raises(ValueError):
            AskRequest(question="a" * 2001)

    def test_a_reasonable_question_is_accepted(self):
        assert AskRequest(question="What is the notice period?").question


# --- Logging discipline ------------------------------------------------------------------
class TestLogging:
    def test_the_question_and_answer_are_not_logged(self, document, caplog):
        secret_question = "Does the indemnity cover the Frobisher acquisition?"

        with caplog.at_level("DEBUG"):
            gate(
                document,
                answer_of(
                    "Either party may terminate with 30 days' written notice.",
                    [{"page": 1, "quote": "30 days' written notice"}],
                ),
                question=secret_question,
            )

        assert "Frobisher" not in caplog.text
        assert "indemnity" not in caplog.text.lower()
        assert "30 days" not in caplog.text
        # Metadata is present.
        assert "doc_test" in caplog.text
        assert f"question_chars={len(secret_question)}" in caplog.text
