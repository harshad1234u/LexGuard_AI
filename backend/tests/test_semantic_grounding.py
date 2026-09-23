"""Phase 10: claim-level semantic grounding, measured against a fixed corpus.

Phase 9 verified that a quote exists and that the numbers around it agree. This
suite exists because that turned out to be insufficient: with no number in
dispute, an answer could invert the meaning of the text it quoted and be
released as `supported`. Four of the eight original adversarial cases did
exactly that.

Both directions are asserted. A verifier that withheld everything would pass
the attack half and be useless, so the legitimate half is equally binding.

No test here calls a model.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import ModelAnswer
from app.verification.qa import gate_answer, verify_answer
from app.verification.semantics import (
    ClaimStatus,
    Modality,
    SemanticIssue,
    check_answer,
    check_claim,
    describes_same_statement,
    evidence_context,
    modality_of,
    parties_in,
    split_claims,
)
from tests.fixtures_adversarial import ATTACKS, LEGITIMATE, Case, GoodCase


class Document:
    """A document the verifier can read, and nothing else."""

    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def run(case: Case | GoodCase):
    """Put one case through verification and the gate, exactly as the API does."""
    document = Document({1: case.page_text})
    evidence = []
    if case.quote:
        page = getattr(case, "page", 1)
        evidence = [{"page": page, "quote": case.quote}]

    answer = ModelAnswer.model_validate(
        {
            "answer": case.answer,
            "evidence": evidence,
            "not_found": getattr(case, "not_found", False),
        }
    )
    return gate_answer(
        document_id="doc_eval",
        question="What does the document say?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


class TestAdversarialCorpus:
    """Every attack must fail closed."""

    @pytest.mark.parametrize("case", ATTACKS, ids=lambda c: c.id)
    def test_attack_is_not_released_as_stated(self, case: Case):
        response = run(case)

        assert str(response.status) in case.allowed_statuses, (
            f"{case.id}: status {response.status} not in {case.allowed_statuses}"
        )
        if case.must_withhold_answer:
            assert response.answer != case.answer, (
                f"{case.id}: the model's own wording was released verbatim"
            )

    @pytest.mark.parametrize("case", ATTACKS, ids=lambda c: c.id)
    def test_attack_text_never_leaks_into_the_response(self, case: Case):
        body = str(run(case).model_dump())
        for fragment in case.must_not_leak:
            assert fragment not in body, f"{case.id}: {fragment!r} reached the client"


class TestLegitimateCorpus:
    """Correct answers must survive. Withholding everything is also a failure."""

    @pytest.mark.parametrize("case", LEGITIMATE, ids=lambda c: c.id)
    def test_legitimate_answer_is_released(self, case: GoodCase):
        response = run(case)

        assert str(response.status) in case.allowed_statuses, (
            f"{case.id}: a correct answer was downgraded to {response.status}"
        )
        assert "couldn't find" not in response.answer, (
            f"{case.id}: a correct answer was withheld entirely"
        )
        for fragment in case.must_contain:
            assert fragment in response.answer, f"{case.id}: lost {fragment!r}"


class TestCorpusIsBalanced:
    """A guard on the guard.

    If every case were an attack, a verifier that refused everything would
    score perfectly. These assertions keep the corpus honest.
    """

    def test_both_families_are_populated(self):
        assert len(ATTACKS) >= 12
        assert len(LEGITIMATE) >= 8

    def test_attacks_cover_every_checked_category(self):
        covered = {case.category for case in ATTACKS}
        assert {
            "numeric", "currency", "date", "actor", "polarity",
            "modality", "conditionality", "evidence", "injection", "isolation",
        } <= covered


# ---------------------------------------------------------------------------
# The individual checks
# ---------------------------------------------------------------------------


class TestClaimSplitting:
    def test_an_answer_splits_into_its_sentences(self):
        claims = split_claims(
            "Either party may terminate with 30 days' notice. The fee is GBP 500."
        )
        assert len(claims) == 2

    def test_fragments_too_short_to_assert_anything_are_ignored(self):
        assert split_claims("Yes. Either party may terminate the agreement.") == [
            "Either party may terminate the agreement."
        ]

    def test_one_verified_quote_does_not_bless_a_second_sentence(self):
        """The property Phase 10 exists to establish."""
        context = "either party may terminate this agreement by providing 30 days written notice"
        verdicts = check_answer(
            "Either party may terminate this agreement. The supplier owes a penalty of damages.",
            [context],
        )
        assert verdicts[0].status is ClaimStatus.SUPPORTED
        assert verdicts[1].status is not ClaimStatus.SUPPORTED


class TestModality:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("The customer may terminate", Modality.PERMISSION),
            ("The customer can terminate", Modality.PERMISSION),
            ("The customer must terminate", Modality.OBLIGATION),
            ("The customer shall terminate", Modality.OBLIGATION),
            ("The customer is required to terminate", Modality.OBLIGATION),
            ("The customer may not terminate", Modality.PROHIBITION),
            ("The customer shall not terminate", Modality.PROHIBITION),
            ("The customer is prohibited from terminating", Modality.PROHIBITION),
            ("Termination occurs on 1 January", Modality.NONE),
        ],
    )
    def test_modality_is_classified(self, text, expected):
        assert modality_of(text) is expected

    def test_may_not_is_a_prohibition_not_a_permission(self):
        """'may not' contains 'may'. Reading it as permission inverts the clause."""
        assert modality_of("The employee may not disclose") is Modality.PROHIBITION


class TestPolarity:
    def test_dropping_a_negation_contradicts(self):
        verdict = check_claim(
            "The employee may disclose confidential information.",
            "the employee must not disclose confidential information",
        )
        assert verdict.status is ClaimStatus.CONTRADICTED

    def test_a_prohibition_phrased_without_not_is_not_a_dropped_negation(self):
        verdict = check_claim(
            "The employee is prohibited from disclosing confidential information.",
            "the employee must not disclose confidential information",
        )
        assert verdict.status is ClaimStatus.SUPPORTED

    def test_adding_a_negation_contradicts(self):
        verdict = check_claim(
            "The customer may not terminate the agreement.",
            "the customer may terminate the agreement",
        )
        assert verdict.status is ClaimStatus.CONTRADICTED


class TestActor:
    def test_a_party_absent_from_the_evidence_is_not_supported(self):
        verdict = check_claim(
            "The supplier may terminate the agreement.",
            "the customer may terminate the agreement",
        )
        assert verdict.status is not ClaimStatus.SUPPORTED
        assert SemanticIssue.ACTOR_NOT_IN_EVIDENCE in verdict.issues

    def test_an_answer_naming_no_party_is_not_penalised(self):
        verdict = check_claim(
            "Termination requires 30 days notice.",
            "the customer may terminate the agreement with 30 days notice",
        )
        assert verdict.status is ClaimStatus.SUPPORTED

    def test_plural_and_synonym_parties_are_the_same_actor(self):
        assert parties_in("the parties agree") == parties_in("either party agrees")
        assert parties_in("the client pays") == parties_in("the customer pays")


class TestConditionality:
    def test_dropping_a_condition_is_not_supported(self):
        verdict = check_claim(
            "The supplier may suspend service.",
            "if payment is overdue the supplier may suspend service",
        )
        assert verdict.status is not ClaimStatus.SUPPORTED
        assert SemanticIssue.CONDITION_DROPPED in verdict.issues

    def test_keeping_the_condition_in_other_words_is_supported(self):
        verdict = check_claim(
            "The supplier may suspend service when payment is overdue.",
            "if payment is overdue the supplier may suspend service",
        )
        assert verdict.status is ClaimStatus.SUPPORTED


class TestContradictionRequiresTheSameStatement:
    """Why a modality difference is not always a contradiction.

    Flipping `may` to `must` in an otherwise identical sentence is the model
    misreading the clause. Saying something else entirely, beside a verified
    quote, is a claim the evidence does not cover. The first discredits the
    whole answer; the second is dropped. Conflating them would let one
    uncovered sentence silence a well-evidenced one.
    """

    def test_a_restated_sentence_with_a_flipped_modal_contradicts(self):
        assert describes_same_statement(
            "The customer must request termination.", "the customer may request termination"
        )
        assert (
            check_claim(
                "The customer must request termination.",
                "the customer may request termination",
            ).status
            is ClaimStatus.CONTRADICTED
        )

    def test_a_different_statement_is_merely_unsupported(self):
        assert not describes_same_statement(
            "The supplier owes liquidated damages.",
            "the customer may request termination",
        )
        assert (
            check_claim(
                "The supplier owes liquidated damages.",
                "the customer may request termination",
            ).status
            is ClaimStatus.UNSUPPORTED
        )


class TestEvidenceContext:
    def test_a_short_quote_is_widened_to_its_sentence(self):
        """A quote alone names no party and grants no permission."""
        context = evidence_context(
            "30 days' written notice",
            "SERVICES AGREEMENT. Either party may terminate this agreement by "
            "providing 30 days' written notice. Fees are due monthly.",
        )
        assert "either party" in context
        assert "may terminate" in context
        # And it stops at the sentence boundary rather than swallowing the page.
        assert "fees are due monthly" not in context

    def test_an_unrelated_negation_elsewhere_on_the_page_is_not_borrowed(self):
        """Using the whole page would make every claim look like a dropped negation."""
        page = (
            "Either party may terminate this agreement by providing 30 days' written notice. "
            "The parties shall not assign this agreement without consent."
        )
        context = evidence_context("30 days' written notice", page)
        assert "shall not assign" not in context


class TestFailClosed:
    def test_an_answer_with_no_claims_is_withheld(self):
        document = Document({1: "Payment is due within 30 days."})
        answer = ModelAnswer.model_validate(
            {"answer": "Yes.", "evidence": [{"page": 1, "quote": "Payment is due"}],
             "not_found": False}
        )
        response = gate_answer(
            document_id="d", question="q", answer=answer,
            verified=verify_answer(answer, document), document=document,
        )
        assert str(response.status) == "not_found"

    def test_claim_counts_are_reported(self):
        """A second, unevidenced sentence is dropped and counted.

        Deliberately carries no figure, so the Phase 5 numeric check cannot
        catch it first and the claim layer is what is being exercised.
        """
        document = Document({1: "Either party may terminate with 30 days' written notice."})
        answer = ModelAnswer.model_validate(
            {
                "answer": (
                    "Either party may terminate with 30 days' written notice. "
                    "The supplier also owes liquidated damages."
                ),
                "evidence": [{"page": 1, "quote": "30 days' written notice"}],
                "not_found": False,
            }
        )
        response = gate_answer(
            document_id="d", question="q", answer=answer,
            verified=verify_answer(answer, document), document=document,
        )
        assert response.claims_checked == 2
        assert response.claims_withheld == 1
        assert "liquidated damages" not in response.answer
