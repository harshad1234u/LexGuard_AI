"""Phase 14: the independent corpus, run as tests.

`eval_independent.py` produces the report; this pins the result so a later
change cannot quietly give some of it back. Two things it asserts that the
report only prints:

* the corpus is intact - every quote occurs in its document, so a "detection"
  is never an artefact of a broken fixture;
* the three known misses are exactly the three that are known. A new miss
  fails here, and a fixed one fails here too, which is the point: the list is
  a record, not a permanent excuse.

Scoring is stricter than `eval_harness.py`. There, an attack counts as
detected when the model's wording does not come back verbatim; with claim-level
splitting that is too generous, because dropping one sentence of two changes
the string while the fabricated sentence still reached the user. Here the
forbidden content must not appear anywhere in the response.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import Evidence, Finding, ModelAnalysis, ModelAnswer
from app.verification.findings import verify_analysis_claims
from app.verification.qa import gate_answer, verify_answer
from app.verification.text import normalize
from tests.fixtures_independent import (
    FAMILIES,
    INDEPENDENT_ALL,
    INDEPENDENT_AMBIGUOUS,
    INDEPENDENT_ATTACKS,
    INDEPENDENT_LEGITIMATE,
    INDEPENDENT_UNRESOLVED,
    IndependentCase,
)

#: Cases this corpus catches the verifier failing, kept red on purpose.
#:
#: Each is analysed in `PHASE_14_REPORT.md` sec. 13, and for two of them a fix
#: was written, measured and reverted because it withheld correct answers about
#: real contract text. Listing them here rather than deleting them keeps the
#: measurement honest: the detection rate below is computed over the whole
#: corpus, including these.
KNOWN_MISSES = {
    # The restriction is a participle phrase qualifying the subject
    # ("Invoices disputed in good faith" -> "Invoices"). A rule for this
    # withheld four correct answers about real FAR and employment text.
    "hc_condition_dispute_carveout_dropped",
    # An item dropped from an enumerated exclusion list. A rule for this
    # withheld six correct answers; shortening a list is also what legitimate
    # summarising does.
    "in_scope_exclusion_omitted",
    # A fabricated second sentence reusing the evidence's vocabulary and a
    # figure genuinely on the page. It scores 0.67 subject-matter overlap,
    # which is exactly the lowest score any legitimate paraphrase in six
    # corpora reaches, so no threshold separates them.
    "ms_two_sentence_answer_one_false",
}


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def run(case: IndependentCase):
    document = Document({1: case.page_text})
    proposal = ModelAnswer(
        answer=case.claim, evidence=[Evidence(page=1, quote=case.quote)]
    )
    return gate_answer(
        document_id="doc_independent",
        question="What does the document say about this?",
        answer=proposal,
        verified=verify_answer(proposal, document),
        document=document,
    )


def handled_safely(case: IndependentCase) -> bool:
    response = run(case)
    body = str(response.model_dump())
    if any(forbidden in body for forbidden in case.must_not_leak):
        return False
    return case.claim.strip() not in response.answer


class TestCorpusIntegrity:
    """A corpus that does not say what it claims to say measures nothing."""

    @pytest.mark.parametrize("case", INDEPENDENT_ALL, ids=lambda c: c.id)
    def test_the_quote_occurs_in_the_document(self, case):
        assert normalize(case.quote) in normalize(case.page_text)

    def test_case_ids_are_unique(self):
        ids = [case.id for case in INDEPENDENT_ALL]
        assert len(ids) == len(set(ids))

    def test_every_family_has_both_halves(self):
        for family in FAMILIES:
            cases = [c for c in INDEPENDENT_ALL if c.contract_family == family]
            assert any(c.family == "attack" for c in cases), family
            assert any(c.family == "legitimate" for c in cases), family

    def test_the_corpus_covers_the_workstream_b_categories(self):
        covered = {case.category for case in INDEPENDENT_ALL}
        required = {
            "polarity", "modality", "actor", "scope", "numeric",
            "conditionality", "temporal", "definition", "injection",
            "multi_sentence",
        }
        assert required <= covered

    def test_known_misses_are_all_real_cases(self):
        assert KNOWN_MISSES <= {case.id for case in INDEPENDENT_ALL}


class TestAdversarialCases:
    @pytest.mark.parametrize(
        "case",
        [c for c in INDEPENDENT_ATTACKS if c.id not in KNOWN_MISSES],
        ids=lambda c: c.id,
    )
    def test_the_manipulation_does_not_reach_the_user(self, case):
        assert handled_safely(case), case.rationale

    @pytest.mark.parametrize("case", INDEPENDENT_UNRESOLVED, ids=lambda c: c.id)
    def test_an_unresolved_case_is_not_answered(self, case):
        """The system must decline rather than supply the missing definition."""
        assert handled_safely(case), case.rationale


class TestLegitimateCases:
    @pytest.mark.parametrize("case", INDEPENDENT_LEGITIMATE, ids=lambda c: c.id)
    def test_a_faithful_answer_is_released(self, case):
        response = run(case)
        assert "couldn't find" not in response.answer, case.rationale
        for required in case.must_contain:
            assert required in response.answer


class TestKnownMisses:
    """Pinned, so the list cannot rot in either direction."""

    @pytest.mark.parametrize("case_id", sorted(KNOWN_MISSES))
    def test_a_known_miss_is_still_missed(self, case_id):
        case = next(c for c in INDEPENDENT_ALL if c.id == case_id)
        assert not handled_safely(case), (
            f"{case_id} now passes - remove it from KNOWN_MISSES and say so in the report"
        )


class TestTheAnalysisPathScoresTheSame:
    """Both surfaces run the same checks, so both should reach the same verdict.

    This is the property Phase 14 had to create: before it, the analysis path
    ran no claim-level check at all and would have shown every one of these.
    """

    @pytest.mark.parametrize(
        "case",
        [
            c
            for c in (*INDEPENDENT_ATTACKS, *INDEPENDENT_UNRESOLVED)
            if c.id not in KNOWN_MISSES
        ],
        ids=lambda c: c.id,
    )
    def test_an_adversarial_claim_is_not_a_verified_finding(self, case):
        document = Document({1: case.page_text})
        analysis = ModelAnalysis(
            findings=[
                Finding(
                    type="clause",
                    claim=case.claim,
                    evidence=Evidence(page=1, quote=case.quote),
                )
            ]
        )
        item = verify_analysis_claims(analysis, document)[0]
        assert not item.is_displayable_as_fact, case.rationale

    @pytest.mark.parametrize("case", INDEPENDENT_LEGITIMATE, ids=lambda c: c.id)
    def test_a_faithful_claim_is_a_verified_finding(self, case):
        document = Document({1: case.page_text})
        analysis = ModelAnalysis(
            findings=[
                Finding(
                    type="clause",
                    claim=case.claim,
                    evidence=Evidence(page=1, quote=case.quote),
                )
            ]
        )
        item = verify_analysis_claims(analysis, document)[0]
        assert item.is_displayable_as_fact, (
            f"{case.id}: {[str(r) for r in item.verification.reasons]}"
        )


class TestMeasuredRates:
    """The headline figures, asserted rather than printed.

    Deliberately not "100%". A threshold that the corpus currently clears
    exactly would turn any future honest measurement into a broken build.
    """

    def test_the_detection_rate_does_not_regress(self):
        scored = [*INDEPENDENT_ATTACKS, *INDEPENDENT_UNRESOLVED]
        detected = sum(1 for case in scored if handled_safely(case))
        assert detected == len(scored) - len(KNOWN_MISSES)
        assert detected / len(scored) >= 0.94

    def test_there_are_no_false_positives(self):
        withheld = [
            case.id
            for case in INDEPENDENT_LEGITIMATE
            if "couldn't find" in run(case).answer
        ]
        assert withheld == []

    def test_ambiguous_cases_are_reported_not_scored(self):
        """Their outcome is recorded in the report; neither answer is a failure."""
        assert INDEPENDENT_AMBIGUOUS
        for case in INDEPENDENT_AMBIGUOUS:
            run(case)  # must not raise
