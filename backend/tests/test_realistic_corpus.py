"""Phase 12: regression over real public-domain contract language.

Every clause here is verbatim FAR text (a US Government work, not subject to
copyright). Its value is that nobody on this project wrote it: it is the only
material in the suite that can show whether the vocabularies generalise or
merely match their own fixtures.

Results from this corpus are reported separately from the synthetic ones and
are never averaged with them.

Also covered here: the role-reversal corpus, which isolates the one category
Phase 11 could not close.

No test here calls a model.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import ModelAnswer
from app.verification.qa import gate_answer, verify_answer
from app.verification.semantics import acting_party, looks_like_injection
from tests.fixtures_realistic import (
    REALISTIC_ALL,
    REALISTIC_ATTACKS,
    REALISTIC_LEGITIMATE,
    SOURCES,
    RealisticCase,
)
from tests.fixtures_roles import ROLE_ALL, ROLE_ATTACKS, ROLE_LEGITIMATE, RoleCase


class Document:
    def __init__(self, text: str):
        self._text = text
        self.page_count = 1

    def page_text(self, page_number: int) -> str | None:
        return self._text if page_number == 1 else None


def gate(page_text: str, claim: str, quote: str):
    document = Document(page_text)
    answer = ModelAnswer.model_validate(
        {"answer": claim, "evidence": [{"page": 1, "quote": quote}], "not_found": False}
    )
    return gate_answer(
        document_id="doc_far",
        question="What does the clause say?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )


def released(response) -> bool:
    return "couldn't find" not in response.answer


# ---------------------------------------------------------------------------
# Real contract language
# ---------------------------------------------------------------------------


class TestRealisticAttacks:
    @pytest.mark.parametrize("case", REALISTIC_ATTACKS, ids=lambda c: c.id)
    def test_a_misstatement_of_real_clause_text_is_not_released(self, case: RealisticCase):
        response = gate(case.source_text, case.claim, case.quote)
        assert not (released(response) and response.answer == case.claim), (
            f"{case.id} ({case.source}): released verbatim as {response.status}"
        )

    @pytest.mark.parametrize(
        "case", [c for c in REALISTIC_ATTACKS if c.must_not_leak], ids=lambda c: c.id
    )
    def test_misstated_content_does_not_reach_the_client(self, case: RealisticCase):
        body = str(gate(case.source_text, case.claim, case.quote).model_dump())
        for fragment in case.must_not_leak:
            assert fragment not in body, f"{case.id}: {fragment!r} leaked"


class TestRealisticLegitimate:
    @pytest.mark.parametrize("case", REALISTIC_LEGITIMATE, ids=lambda c: c.id)
    def test_a_fair_answer_about_real_clause_text_survives(self, case: RealisticCase):
        response = gate(case.source_text, case.claim, case.quote)
        assert released(response), (
            f"{case.id} ({case.source}): a correct answer about real contract "
            f"language was withheld ({response.status})"
        )

    @pytest.mark.parametrize(
        "case", [c for c in REALISTIC_LEGITIMATE if c.must_contain], ids=lambda c: c.id
    )
    def test_required_content_survives(self, case: RealisticCase):
        answer = gate(case.source_text, case.claim, case.quote).answer
        for fragment in case.must_contain:
            assert fragment in answer, f"{case.id}: lost {fragment!r}"

    def test_bare_imperative_requirements_are_not_treated_as_injection(self):
        """FAR 52.204-21 states requirements as commands with no party subject.

        "Sanitize or destroy information system media before disposal" is a
        real federal contract requirement and looks exactly like an instruction
        aimed at an assistant. Getting this wrong would make the tool refuse to
        answer questions about a whole class of genuine clauses.
        """
        for case in REALISTIC_LEGITIMATE:
            if case.category != "legit_imperative":
                continue
            assert not looks_like_injection(case.source_text), (
                f"{case.id}: real FAR requirement flagged as injection"
            )
            assert released(gate(case.source_text, case.claim, case.quote))


class TestProvenance:
    """The corpus must stay attributable."""

    def test_every_case_cites_a_source(self):
        for case in REALISTIC_ALL:
            assert case.source.startswith("FAR "), case.id
            assert case.source.split("(")[0].strip() in SOURCES, case.id

    def test_every_quote_occurs_in_its_source_text(self):
        """A fixture whose quote is not in its clause would test nothing."""
        from app.verification.text import normalize

        for case in REALISTIC_ALL:
            assert normalize(case.quote) in normalize(case.source_text), (
                f"{case.id}: quote is not present in the cited clause"
            )


# ---------------------------------------------------------------------------
# Role reversal
# ---------------------------------------------------------------------------

#: Empty since Phase 13. Named-entity reversal ("ABC Ltd" vs "XYZ Ltd") was the
#: last entry: the evidence context is normalised to lower case, so Phase 12
#: concluded a company name was indistinguishable from any other word there.
#: That turned out to be the wrong conclusion - capitalisation is not the only
#: signal. A name in the subject slot of an obligation verb is decidable
#: without it, which is what `named_parties` reads.
ROLE_KNOWN_GAPS: set[str] = set()


class TestRoleReversal:
    @pytest.mark.parametrize(
        "case",
        [c for c in ROLE_ATTACKS if c.id not in ROLE_KNOWN_GAPS],
        ids=lambda c: c.id,
    )
    def test_a_reversed_role_is_not_released(self, case: RoleCase):
        response = gate(case.evidence, case.claim, case.evidence)
        assert not (released(response) and response.answer == case.claim), (
            f"{case.id} ({case.construction}): released a role reversal"
        )

    @pytest.mark.parametrize("case", ROLE_LEGITIMATE, ids=lambda c: c.id)
    def test_a_faithful_answer_is_not_mistaken_for_a_reversal(self, case: RoleCase):
        response = gate(case.evidence, case.claim, case.evidence)
        assert released(response), (
            f"{case.id} ({case.construction}): a faithful answer was withheld"
        )

    def test_named_entity_reversal_is_detected(self):
        """Phase 12's open gap, closed in Phase 13.

        This test was previously written inverted - it asserted the reversal
        was released, so that the limitation list could not go stale. It has
        been turned the right way up rather than removed, so the behaviour it
        guarded is still guarded, now in the other direction.
        """
        case = next(c for c in ROLE_ALL if c.id == "role_named_entities")
        response = gate(case.evidence, case.claim, case.evidence)
        assert not (released(response) and response.answer == case.claim), (
            "a reversal between two named companies was released verbatim"
        )

    def test_the_matching_named_entity_answer_still_survives(self):
        """The other half of the same question.

        Detecting the reversal is worthless if the faithful answer about the
        same two companies is withheld alongside it.
        """
        case = next(c for c in ROLE_ALL if c.id == "role_legit_named_entities")
        assert released(gate(case.evidence, case.claim, case.evidence))


class TestActingParty:
    """The role binding itself, unit level."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("The Supplier shall deliver the goods.", "supplier"),
            ("the supplier shall deliver the goods to the customer", "supplier"),
            ("The goods shall be delivered by the Supplier.", "supplier"),
            ("The invoice shall be paid by the Buyer.", "buyer"),
            ("The Government shall pay contract price.", "government"),
            ("Travel expenses are reimbursed.", None),
            ("Interest applies at 2% per month.", None),
        ],
    )
    def test_the_acting_party_is_identified(self, text, expected):
        assert acting_party(text) == expected

    def test_passive_voice_is_not_read_as_a_reversal(self):
        """The case a word-order rule gets wrong.

        "The goods shall be delivered by the Supplier" names the goods first
        and the Supplier second, but the Supplier is still the one acting.
        """
        assert acting_party("The Supplier shall deliver the goods.") == acting_party(
            "The goods shall be delivered by the Supplier."
        )

    def test_a_named_organisation_is_identified_as_the_actor(self):
        """Phase 12 returned None here and called it "no guess".

        On real agreements that was not caution, it was blindness: contracts
        define their sides once and then say "Castlight shall notify Anthem"
        for the rest of the document. A name in the subject slot of an
        obligation verb is as decidable as a role noun.
        """
        assert acting_party("Acme Holdings shall deliver the goods.") == "acme holdings"
        assert acting_party("Castlight shall notify Anthem within 24 hours.") == "castlight"

    def test_text_that_settles_nothing_still_yields_no_verdict(self):
        """The half of the old test that must not change.

        Widening the vocabulary is only safe while sentences that identify no
        actor keep returning None, so the caller falls back to the presence
        check instead of acting on a guess.
        """
        assert acting_party("Travel expenses are reimbursed.") is None
        assert acting_party("Interest applies at 2% per month.") is None
        # A capitalised defined term is not a party to the agreement.
        assert acting_party("This Agreement shall commence on 1 April 2026.") is None
        assert acting_party("The Release must be executed within 90 days.") is None
