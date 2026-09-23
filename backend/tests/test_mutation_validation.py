"""Phase 14 workstream D: mutation-style validation, as tests.

Ordinary tests ask whether a manipulation someone thought of is caught.
Mutation testing asks the complementary question - whether *changing the
meaning at all* changes the outcome - by taking statements this corpus says
are faithful, altering exactly one semantic property, and leaving the evidence
untouched. A mutation that is not detected is a change of meaning the
application cannot see.

The transforms live in `eval_independent.py` so the report and the tests
cannot disagree about what was measured.
"""

from __future__ import annotations

import pytest

from eval_independent import MUTATIONS, mutate
from tests.fixtures_independent import INDEPENDENT_LEGITIMATE

#: The one mutation the harness applies that does not actually change meaning:
#: removing "up to" from "up to a maximum of £75,000.00" leaves "a maximum of",
#: which is the same limit. Releasing it is correct, and it is excluded from
#: the detection requirement rather than counted as a miss the checks should
#: have caught. It is still reported in the coverage table.
NON_SEMANTIC_MUTATIONS = {("scope_broadened", "cn_conditionality_faithful")}


def _all_mutations():
    for case in INDEPENDENT_LEGITIMATE:
        for name, transform in MUTATIONS:
            outcome = mutate(case, transform)
            if outcome is not None:
                yield name, case, outcome[0], outcome[1]


MUTATION_RESULTS = list(_all_mutations())


class TestMutationCoverage:
    @pytest.mark.parametrize(
        "name,case,mutated,detected",
        MUTATION_RESULTS,
        ids=[f"{name}-{case.id}" for name, case, _, _ in MUTATION_RESULTS],
    )
    def test_a_changed_meaning_changes_the_outcome(self, name, case, mutated, detected):
        if (name, case.id) in NON_SEMANTIC_MUTATIONS:
            pytest.skip("the transform does not change the meaning of this sentence")
        assert detected, f"{name} on {case.id} was released: {mutated}"

    def test_the_run_is_large_enough_to_mean_something(self):
        """A shrinking mutation set would make the rate look good for free."""
        assert len(MUTATION_RESULTS) >= 80

    def test_every_semantic_axis_is_exercised(self):
        applied = {name for name, _, _, _ in MUTATION_RESULTS}
        assert {
            "polarity",
            "modality",
            "actor",
            "quantity",
            "currency",
            "condition_removed",
            "scope_broadened",
            "limit_removed",
        } <= applied

    def test_the_detection_rate_does_not_regress(self):
        detected = sum(1 for _, _, _, ok in MUTATION_RESULTS if ok)
        assert detected / len(MUTATION_RESULTS) >= 0.98
