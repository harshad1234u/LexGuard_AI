"""Phase 13 regressions: cross-domain contracts, named entities, definitions.

`eval_harness.py --corpora` reports rates; this file pins behaviour so that a
regression fails the build. Three new corpora are covered, each scored on its
own and never averaged with the others:

    fixtures_contracts.py   real SaaS, employment, lease and DPA clause text
    fixtures_entities.py    the named-entity role matrix (synthetic)
    fixtures_definitions.py defined terms and cross-references

Alongside them sit unit-level regressions for each production change Phase 13
made, written against the case that exposed the defect. Every one of these
failed before its fix and passes after it.

No test here calls a model.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import ModelAnswer
from app.verification.numeric import Comparison, compare_numbers
from app.verification.qa import gate_answer, verify_answer
from app.verification.semantics import (
    UNIVERSAL_SCOPE,
    SemanticIssue,
    _has_any,
    acting_party,
    check_claim,
    evidence_context,
    named_parties,
    parties_in,
)
from app.verification.text import normalize
from tests.fixtures_contracts import (
    CONTRACT_ALL,
    CONTRACT_ATTACKS,
    CONTRACT_LEGITIMATE,
    DOCUMENT_FAMILIES,
    SOURCE_URLS,
    ContractCase,
)
from tests.fixtures_definitions import (
    DEFINITION_ATTACKS,
    DEFINITION_LEGITIMATE,
    DefinitionCase,
)
from tests.fixtures_entities import (
    ENTITY_ATTACKS,
    ENTITY_LEGITIMATE,
    EntityCase,
)


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
        document_id="doc_phase13",
        question="What does the clause say?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )


def released(response) -> bool:
    return "couldn't find" not in response.answer


# ===========================================================================
# 1. Real contract text outside the FAR
# ===========================================================================


class TestCrossDomainAttacks:
    @pytest.mark.parametrize("case", CONTRACT_ATTACKS, ids=lambda c: c.id)
    def test_a_misstatement_of_real_clause_text_is_not_released(
        self, case: ContractCase
    ):
        response = gate(case.source_text, case.claim, case.quote)
        assert not (released(response) and response.answer == case.claim), (
            f"{case.id} ({case.document_family}, {case.attack_type}): "
            f"released verbatim as {response.status}"
        )

    @pytest.mark.parametrize(
        "case", [c for c in CONTRACT_ATTACKS if c.must_not_leak], ids=lambda c: c.id
    )
    def test_misstated_content_does_not_reach_the_client(self, case: ContractCase):
        body = str(gate(case.source_text, case.claim, case.quote).model_dump())
        for fragment in case.must_not_leak:
            assert fragment not in body, f"{case.id}: {fragment!r} leaked"


class TestCrossDomainLegitimate:
    @pytest.mark.parametrize("case", CONTRACT_LEGITIMATE, ids=lambda c: c.id)
    def test_a_fair_answer_about_real_clause_text_survives(self, case: ContractCase):
        response = gate(case.source_text, case.claim, case.quote)
        assert released(response), (
            f"{case.id} ({case.document_family}): a correct answer about real "
            f"contract language was withheld ({response.status})"
        )

    @pytest.mark.parametrize(
        "case", [c for c in CONTRACT_LEGITIMATE if c.must_contain], ids=lambda c: c.id
    )
    def test_required_content_survives(self, case: ContractCase):
        answer = gate(case.source_text, case.claim, case.quote).answer
        for fragment in case.must_contain:
            assert fragment in answer, f"{case.id}: lost {fragment!r}"


class TestCrossDomainProvenance:
    """A corpus that cannot be traced back to its source proves nothing."""

    def test_every_case_records_a_usable_source(self):
        for case in CONTRACT_ALL:
            assert case.source_url in SOURCE_URLS, case.id
            assert case.source_section, case.id
            assert case.source_title, case.id
            assert case.jurisdiction, case.id

    def test_every_quote_occurs_in_its_source_text(self):
        for case in CONTRACT_ALL:
            assert normalize(case.quote) in normalize(case.source_text), (
                f"{case.id}: quote is not present in the cited clause"
            )

    def test_every_attack_names_its_transformation(self):
        """Adversarial cases are transformations we applied, not found text."""
        for case in CONTRACT_ATTACKS:
            assert case.attack_type, case.id
        for case in CONTRACT_LEGITIMATE:
            assert case.attack_type is None, case.id

    def test_all_four_document_families_are_present(self):
        present = {case.document_family for case in CONTRACT_ALL}
        assert present == set(DOCUMENT_FAMILIES)

    def test_each_family_carries_both_attacks_and_legitimate_cases(self):
        """A family with no legitimate cases would hide false positives."""
        for family in DOCUMENT_FAMILIES:
            cases = [c for c in CONTRACT_ALL if c.document_family == family]
            assert any(c.family == "attack" for c in cases), family
            assert any(c.family == "legitimate" for c in cases), family


# ===========================================================================
# 2. Named entities
# ===========================================================================


class TestNamedEntityAttacks:
    @pytest.mark.parametrize(
        "case", [c for c in ENTITY_ATTACKS if not c.known_gap], ids=lambda c: c.id
    )
    def test_a_reversed_or_substituted_entity_is_not_released(self, case: EntityCase):
        response = gate(case.evidence, case.claim, case.evidence)
        assert not (released(response) and response.answer == case.claim), (
            f"{case.id} ({case.construction}): released a role reversal"
        )

    def test_the_known_gap_list_is_empty(self):
        """Pinned so that adding a gap is a deliberate, visible act."""
        assert [c.id for c in ENTITY_ATTACKS if c.known_gap] == []


class TestNamedEntityLegitimate:
    @pytest.mark.parametrize("case", ENTITY_LEGITIMATE, ids=lambda c: c.id)
    def test_a_faithful_answer_is_not_mistaken_for_a_reversal(self, case: EntityCase):
        response = gate(case.evidence, case.claim, case.evidence)
        assert released(response), (
            f"{case.id} ({case.construction}): a faithful answer was withheld "
            f"({response.status})"
        )


class TestNamedPartyExtraction:
    """The extractor itself, unit level."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Castlight shall notify Anthem within 24 hours.", {"castlight"}),
            ("Northwind Ltd shall reimburse Contoso Ltd.", {"northwind ltd"}),
            ("The monthly report shall be prepared by Northwind Ltd.", {"northwind ltd"}),
            # Role nouns are PARTY_TERMS' job, not this one.
            ("The Supplier shall deliver the goods.", set()),
            ("The data importer shall process the personal data.", set()),
            # Capitalised terms that are not sides of the contract.
            ("This Agreement shall commence on 1 April 2026.", set()),
            ("The Release must be executed within 90 days.", set()),
            ("The fees shall be set out in Schedule 1.", set()),
            # Passive agents that are a manner, not an actor.
            ("Changes may be made only by written agreement of the parties.", set()),
            # Nothing to find.
            ("Travel expenses are reimbursed.", set()),
        ],
    )
    def test_named_parties_are_recognised_without_capitalisation(self, text, expected):
        """The evidence sentence arrives casefolded, so case cannot be relied on."""
        assert named_parties(text.lower()) == expected

    def test_a_company_name_containing_a_role_noun_is_read_as_a_name(self):
        assert acting_party("contractor services ltd shall invoice supplier holdings ltd") == (
            "contractor services ltd"
        )

    def test_a_third_party_is_not_a_party_to_the_agreement(self):
        """"Claims made by a third party" used to yield "party" as the actor.

        That spurious agreement masked a real reversal between two named
        companies in the SaaS corpus.
        """
        assert "party" not in parties_in(
            "demandware shall indemnify neckermann.de against claims made by a third party"
        )

    def test_a_passive_subject_is_not_harvested_as_an_actor(self):
        """"Invoices shall be paid by the customer" - invoices are not a party."""
        assert named_parties("invoices shall be paid by the customer within 30 days") == set()


# ===========================================================================
# 3. Definitions and cross-references
# ===========================================================================


class TestDefinitionAttacks:
    @pytest.mark.parametrize("case", DEFINITION_ATTACKS, ids=lambda c: c.id)
    def test_meaning_held_elsewhere_is_not_invented(self, case: DefinitionCase):
        response = gate(case.page_text, case.claim, case.quote)
        assert not (released(response) and response.answer == case.claim), (
            f"{case.id} ({case.construction}): released a claim resting on text "
            f"that is not in evidence"
        )

    @pytest.mark.parametrize(
        "case", [c for c in DEFINITION_ATTACKS if c.must_not_leak], ids=lambda c: c.id
    )
    def test_invented_content_does_not_reach_the_client(self, case: DefinitionCase):
        body = str(gate(case.page_text, case.claim, case.quote).model_dump())
        for fragment in case.must_not_leak:
            assert fragment not in body, f"{case.id}: {fragment!r} leaked"


class TestDefinitionLegitimate:
    @pytest.mark.parametrize("case", DEFINITION_LEGITIMATE, ids=lambda c: c.id)
    def test_reporting_the_pointer_is_allowed(self, case: DefinitionCase):
        response = gate(case.page_text, case.claim, case.quote)
        assert released(response), (
            f"{case.id}: an answer that correctly reports where the substance "
            f"lives was withheld ({response.status})"
        )

    @pytest.mark.parametrize(
        "case", [c for c in DEFINITION_LEGITIMATE if c.must_contain], ids=lambda c: c.id
    )
    def test_the_reference_itself_survives(self, case: DefinitionCase):
        """The citation is the useful part. Dropping it defeats the answer."""
        answer = gate(case.page_text, case.claim, case.quote).answer
        for fragment in case.must_contain:
            assert fragment in answer, f"{case.id}: lost the reference {fragment!r}"

    def test_the_quote_and_its_page_are_preserved(self):
        case = DEFINITION_LEGITIMATE[0]
        response = gate(case.page_text, case.claim, case.quote)
        assert response.evidence, "evidence was dropped from a released answer"
        assert response.evidence[0].quote == case.quote
        assert response.evidence[0].page == 1


# ===========================================================================
# 4. Regressions for each Phase 13 production change
#
# Each test below reproduces the case that exposed a defect. Each one failed
# before its fix.
# ===========================================================================


class TestWordBoundaryVocabularyMatching:
    """Vocabularies matched as substrings, which disabled a whole check.

    "all" is a substring of "shall", so every clause containing "shall" - which
    is nearly every clause in nearly every contract - was read as carrying a
    universal quantifier. Scope comparison then saw "universal on both sides"
    and raised nothing.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "the data importer shall inform data subjects",
            "the Company shall pay the Executive",
            "generally applicable terms",  # "all" inside "generally"
            "the Company may terminate",  # "any" inside "Company"
        ],
    )
    def test_a_word_fragment_is_not_a_vocabulary_hit(self, text):
        assert not _has_any(text, UNIVERSAL_SCOPE)

    @pytest.mark.parametrize(
        "text", ["at all times", "for any purpose", "every requirement", "the entire premises"]
    )
    def test_a_real_quantifier_is_still_found(self, text):
        assert _has_any(text, UNIVERSAL_SCOPE)

    def test_scope_broadening_is_caught_on_a_clause_containing_shall(self):
        context = "the data importer shall inform data subjects of a contact point"
        verdict = check_claim(
            "The data importer shall inform data subjects of every detail.", context
        )
        assert SemanticIssue.SCOPE_BROADENED in verdict.issues


class TestSentenceBoundaryAroundNumbers:
    """A dot inside a number truncated the evidence context.

    The context for a quote following "($1,400,000.00) per annum" was the
    fragment "00) per annum" - no actor, no modality, no amount - and every
    downstream check then ran on that fragment and found nothing to object to.
    """

    def test_a_decimal_does_not_end_the_sentence(self):
        page = (
            "During the Term of Employment, the Company shall pay to the Executive "
            "a salary at a rate of not less than one million and four hundred "
            "thousand dollars ($1,400,000.00) per annum."
        )
        context = evidence_context("per annum", page)
        assert "the company shall pay" in context
        assert "$1,400,000.00" in context

    def test_a_section_number_does_not_end_the_sentence(self):
        page = (
            "Subject to Section 9.4, the Supplier shall replace defective goods "
            "at its own cost."
        )
        context = evidence_context(
            "the Supplier shall replace defective goods at its own cost", page
        )
        assert context.startswith("subject to section 9.4")

    def test_a_percentage_does_not_end_the_sentence(self):
        page = (
            "Landlord may impose a Late Charge equal to one-half of one percent "
            "(0.5%) of the past due payment per day."
        )
        assert "landlord may" in evidence_context("of the past due payment per day", page)

    def test_a_real_sentence_end_is_still_a_boundary(self):
        """The fix must not swallow the next sentence."""
        page = (
            "Either party may terminate on 30 days' notice. "
            "The parties shall not assign this agreement without consent."
        )
        assert "shall not assign" not in evidence_context("30 days' notice", page)


class TestSpelledOutDurations:
    """"within one month" carries a deadline with no digits anywhere.

    Real EU Standard Contractual Clauses text does exactly this, and a claim
    restating it as "six months" changed the deadline sixfold with no value in
    dispute as far as the verifier could tell.
    """

    def test_a_changed_spelled_out_duration_is_a_mismatch(self):
        assert (
            compare_numbers("within six months of suspension", "within one month of suspension").result
            is Comparison.MISMATCH
        )

    def test_an_unchanged_spelled_out_duration_matches(self):
        assert (
            compare_numbers("within one month", "within one month").result is Comparison.MATCH
        )

    def test_the_digit_form_still_wins_where_a_drafter_gave_both(self):
        """"sixty (60) days" is one deadline, not two."""
        assert (
            compare_numbers("not less than sixty (60) days", "not less than 60 days").result
            is Comparison.MATCH
        )

    def test_no_unit_conversion_is_performed(self):
        """One month is not thirty days; the document's own unit is the one that counts."""
        assert (
            compare_numbers("within one month", "within 30 days").result is Comparison.MISMATCH
        )


class TestExceptionsAndCrossReferences:
    def test_a_dropped_carve_out_is_reported(self):
        verdict = check_claim(
            "Tenant shall keep the Premises in good order, condition and repair.",
            "tenant shall keep the premises in good order, condition and repair, "
            "ordinary wear and tear excepted",
        )
        assert SemanticIssue.EXCEPTION_DROPPED in verdict.issues

    def test_a_preserved_carve_out_is_not_reported(self):
        verdict = check_claim(
            "Tenant shall keep the Premises in repair, ordinary wear and tear excepted.",
            "tenant shall keep the premises in repair, ordinary wear and tear excepted",
        )
        assert SemanticIssue.EXCEPTION_DROPPED not in verdict.issues

    def test_a_universal_replacing_a_cross_reference_is_reported(self):
        verdict = check_claim(
            "Demandware will maintain the Platform so that it complies with every requirement.",
            "demandware will maintain the platform so that it complies with the "
            "specifications set forth in exhibit a",
        )
        assert SemanticIssue.UNRESOLVED_REFERENCE_DROPPED in verdict.issues

    def test_summarising_without_a_universal_is_not_penalised(self):
        """Dropping a citation while restating the clause faithfully is allowed.

        Flagging it withheld correct answers about real EU and federal clauses,
        which is why the rule requires the answer to assert something universal.
        """
        verdict = check_claim(
            "The data importer shall notify the data exporter and the supervisory authority.",
            "the data importer shall notify the data exporter and the competent "
            "supervisory authority pursuant to clause 13",
        )
        assert SemanticIssue.UNRESOLVED_REFERENCE_DROPPED not in verdict.issues

    def test_a_schedule_named_in_is_not_a_cross_reference(self):
        """"any Order Schedule in whole or in part" points at no Schedule "in"."""
        verdict = check_claim(
            "Either party may terminate this Agreement or any Order Schedule.",
            "either party may terminate this agreement and any order schedule in "
            "whole or in part",
        )
        assert SemanticIssue.UNRESOLVED_REFERENCE_DROPPED not in verdict.issues


class TestMultiSentenceEvidence:
    """A quote spanning two sentences made the context the wrong unit.

    The actor of one sentence was compared against the claim about the other,
    which reported a role reversal against a verbatim answer.
    """

    def test_a_verbatim_two_sentence_answer_survives(self):
        page = "Northwind shall deliver the goods. Contoso shall inspect them within five days."
        response = gate(page, page, page)
        assert released(response)

    def test_a_reversal_inside_a_two_sentence_answer_is_still_caught(self):
        """The pairing must not become a way to smuggle a reversal through."""
        page = "Northwind shall deliver the goods. Contoso shall inspect them within five days."
        claim = "Northwind shall deliver the goods. Northwind shall inspect them within five days."
        response = gate(page, claim, page)
        assert not (released(response) and response.answer == claim)


class TestAnswerLevelNumericGranularity:
    """A discovered, pre-existing limitation, pinned rather than fixed.

    Numeric verification runs against the WHOLE answer, while the semantic
    checks run per sentence. So an unsupported figure anywhere in a
    multi-sentence answer rejects the evidence and withholds everything,
    including the sentence that was properly supported.

    This is fail-closed, so it is safe; it is also less useful than the
    sentence-level dropping the gate performs everywhere else. Phase 13 did not
    change it - aligning the two granularities touches the verification core
    and belongs in its own phase, with its own measurement. The behaviour is
    asserted here so that it is a known, measured property.
    """

    PAGE = "Either party may terminate this agreement by providing 30 days' written notice."

    def test_a_supported_sentence_survives_an_unsupported_one(self):
        response = gate(
            self.PAGE,
            "Either party may terminate with 30 days' written notice. "
            "Records shall be retained after termination.",
            "30 days' written notice",
        )
        assert released(response)
        assert "30 days" in response.answer
        assert "Records shall be retained" not in response.answer

    def test_an_unsupported_figure_elsewhere_withholds_the_whole_answer(self):
        """The limitation itself. Both spellings behave the same way."""
        for second_sentence in (
            "Records shall be retained for 7 years.",
            "Records shall be retained for seven years.",
        ):
            response = gate(
                self.PAGE,
                f"Either party may terminate with 30 days' written notice. {second_sentence}",
                "30 days' written notice",
            )
            assert not released(response), (
                f"granularity behaviour changed for {second_sentence!r} - if this "
                f"was deliberate, update the Phase 13 limitation list"
            )
