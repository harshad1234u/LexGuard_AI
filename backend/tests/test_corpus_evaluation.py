"""Phase 11: the expanded corpus, as a regression suite.

`eval_harness.py` reports rates; this file pins behaviour so a regression fails
the build. Cases in categories the implementation does not claim to cover are
marked `known_gap` and asserted as *currently failing* rather than skipped - if
one starts passing, that is worth noticing too, and the assertion says so.

Both families are enforced:

    an attack released      -> the verifier is unsafe
    a legitimate answer withheld -> the verifier is unusable

No test here calls a model.
"""

from __future__ import annotations

import pytest

from app.schemas.findings import ModelAnswer
from app.verification.qa import gate_answer, verify_answer
from tests.fixtures_corpus import ALL_CASES, ATTACK_CASES, LEGITIMATE_ALL, EvalCase


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def run(case: EvalCase):
    document = Document({1: case.page_text})
    evidence = [{"page": case.page, "quote": case.quote}] if case.quote else []
    answer = ModelAnswer.model_validate(
        {"answer": case.answer, "evidence": evidence, "not_found": case.not_found}
    )
    return gate_answer(
        document_id="doc_eval",
        question="What does the document say?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )


def released_verbatim(response, case: EvalCase) -> bool:
    return "couldn't find" not in response.answer and response.answer == case.answer


COVERED_ATTACKS = [c for c in ATTACK_CASES if not c.known_gap]
KNOWN_GAPS = [c for c in ATTACK_CASES if c.known_gap]


class TestAttacksInCoveredCategories:
    """Attacks the implementation claims to handle."""

    @pytest.mark.parametrize("case", COVERED_ATTACKS, ids=lambda c: c.id)
    def test_the_attackers_wording_is_not_released(self, case: EvalCase):
        response = run(case)
        assert not released_verbatim(response, case), (
            f"{case.id}: released verbatim as {response.status}"
        )

    @pytest.mark.parametrize(
        "case", [c for c in COVERED_ATTACKS if c.must_not_leak], ids=lambda c: c.id
    )
    def test_forbidden_text_does_not_reach_the_client(self, case: EvalCase):
        body = str(run(case).model_dump())
        for fragment in case.must_not_leak:
            assert fragment not in body, f"{case.id}: {fragment!r} leaked"


class TestKnownGaps:
    """The documented gap list must match reality, in both directions.

    Cases marked as gaps are recorded rather than skipped, and the assertion
    is inverted: a gap that starts passing fails this test, so the limitation
    list in the docs cannot drift out of date. Phase 12 emptied this list by
    closing role reversal; the test still guards against it being repopulated
    incorrectly.
    """

    def test_every_marked_gap_is_genuinely_still_failing(self):
        wrongly_marked = [
            case.id for case in KNOWN_GAPS if not released_verbatim(run(case), case)
        ]
        assert wrongly_marked == [], (
            f"{wrongly_marked} are marked `known_gap=True` but now pass. Good news - "
            f"remove the flag and update the limitations in "
            f"docs/04_SECURITY_GROUNDING.md."
        )

    def test_the_gap_list_is_empty_on_this_corpus(self):
        """Phase 12 closed the last one. Pinned so a regression is visible."""
        assert [case.id for case in KNOWN_GAPS] == []


class TestLegitimateAnswersSurvive:
    """The other half. A verifier that refuses everything is not safe, it is broken."""

    @pytest.mark.parametrize("case", LEGITIMATE_ALL, ids=lambda c: c.id)
    def test_a_fair_answer_is_released(self, case: EvalCase):
        response = run(case)
        assert "couldn't find" not in response.answer, (
            f"{case.id}: a legitimate answer was withheld ({response.status})"
        )

    @pytest.mark.parametrize(
        "case", [c for c in LEGITIMATE_ALL if c.must_contain], ids=lambda c: c.id
    )
    def test_required_content_survives(self, case: EvalCase):
        answer = run(case).answer
        for fragment in case.must_contain:
            assert fragment in answer, f"{case.id}: lost {fragment!r}"


class TestCorpusShape:
    """Guards on the corpus itself, so the measurement stays honest."""

    def test_both_families_are_substantial(self):
        assert len(ATTACK_CASES) >= 35
        assert len(LEGITIMATE_ALL) >= 25

    def test_every_required_category_is_present(self):
        categories = {case.category for case in ALL_CASES}
        assert {
            "modality", "polarity", "conditionality", "actor", "scope",
            "temporal", "cross_reference", "multi_sentence",
        } <= categories
        assert {
            "legit_negation", "legit_conditionality", "legit_modality",
            "legit_exception", "legit_parties", "legit_imperative",
            "legit_paraphrase",
        } <= categories

    def test_case_ids_are_unique(self):
        ids = [case.id for case in ALL_CASES]
        assert len(ids) == len(set(ids))

    def test_the_false_positive_rate_is_zero_on_this_corpus(self):
        """No legitimate case may be withheld.

        A single number, asserted, so the trade-off cannot silently drift
        towards refusing everything.
        """
        withheld = [
            case.id
            for case in LEGITIMATE_ALL
            if "couldn't find" in run(case).answer
        ]
        assert withheld == [], f"legitimate answers withheld: {withheld}"


class TestThresholdSensitivity:
    """What the overlap threshold actually changes.

    Measured rather than assumed: it decides whether a divergent claim
    *poisons* an answer or is merely *dropped* from it. Both withhold the
    claim, so it is not a safety parameter - it trades caution against
    usefulness in multi-sentence answers.
    """

    def test_no_unsupported_claim_is_released_at_any_threshold(self):
        from app.verification import semantics

        case = next(c for c in ALL_CASES if c.id == "multi_borderline_overlap")
        original = semantics.SAME_STATEMENT_OVERLAP
        try:
            for value in (0.4, 0.5, 0.6, 0.7, 0.8):
                semantics.SAME_STATEMENT_OVERLAP = value
                answer = run(case).answer
                # The unsupported sentence must never appear, whatever the value.
                assert "written termination approval" not in answer, (
                    f"threshold {value} released an unsupported claim"
                )
        finally:
            semantics.SAME_STATEMENT_OVERLAP = original

    def test_the_threshold_changes_how_much_is_released(self):
        """Documents the observable effect, so a change is deliberate."""
        from app.verification import semantics

        case = next(c for c in ALL_CASES if c.id == "multi_borderline_overlap")
        original = semantics.SAME_STATEMENT_OVERLAP
        try:
            semantics.SAME_STATEMENT_OVERLAP = 0.6
            strict = run(case)
            semantics.SAME_STATEMENT_OVERLAP = 0.7
            lenient = run(case)
        finally:
            semantics.SAME_STATEMENT_OVERLAP = original

        assert str(strict.status) == "not_found"
        assert str(lenient.status) == "partially_supported"
        assert "may request termination" in lenient.answer
