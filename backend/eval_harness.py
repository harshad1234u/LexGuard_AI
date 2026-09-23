"""Phase 11: false-positive / false-negative evaluation.

Runs the expanded corpus through the real verification stack and reports what
actually happened, per case and per category.

    .venv/Scripts/python eval_harness.py              full report
    .venv/Scripts/python eval_harness.py --failures   only the failures
    .venv/Scripts/python eval_harness.py --threshold  overlap sweep

Two error types, counted separately because they trade off against each other:

    FALSE NEGATIVE  an attack was released       (unsafe)
    FALSE POSITIVE  a legitimate answer withheld (useless)

Reporting only one would reward a degenerate verifier: refusing everything
gives a perfect false-negative rate.

No model is called. Every "model answer" is hand-written. These figures
describe the application's grounding boundary against synthetic input; they are
not a measurement of Nemotron's accuracy and must not be reported as one.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.schemas.findings import ModelAnswer
from app.verification.qa import gate_answer, verify_answer
from tests.fixtures_corpus import ALL_CASES, EvalCase


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


class Outcome:
    """What the application did with one case, and whether that was right."""

    __slots__ = ("case", "status", "answer", "released", "correct", "reason")

    def __init__(self, case: EvalCase, response):
        self.case = case
        self.status = str(response.status)
        self.answer = response.answer
        self.released = "couldn't find" not in response.answer

        body = str(response.model_dump())
        leaked = [f for f in case.must_not_leak if f in body]
        missing = [f for f in case.must_contain if f not in response.answer]

        if case.family == "attack":
            # An attack is handled correctly when the model's own wording does
            # not reach the user and nothing forbidden leaks.
            self.correct = (not self.released or self.answer != case.answer) and not leaked
            if leaked:
                self.reason = f"leaked {leaked!r}"
            elif self.released and self.answer == case.answer:
                self.reason = "released the attacker's wording verbatim"
            else:
                self.reason = ""
        else:
            self.correct = self.released and not missing
            if not self.released:
                self.reason = "a legitimate answer was withheld entirely"
            elif missing:
                self.reason = f"dropped required content {missing!r}"
            else:
                self.reason = ""

    @property
    def error_type(self) -> str:
        if self.correct:
            return ""
        return "FALSE NEGATIVE" if self.case.family == "attack" else "FALSE POSITIVE"


def evaluate(case: EvalCase) -> Outcome:
    document = Document({1: case.page_text})
    evidence = [{"page": case.page, "quote": case.quote}] if case.quote else []
    answer = ModelAnswer.model_validate(
        {"answer": case.answer, "evidence": evidence, "not_found": case.not_found}
    )
    response = gate_answer(
        document_id="doc_eval",
        question="What does the document say?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )
    return Outcome(case, response)


def run_all() -> list[Outcome]:
    return [evaluate(case) for case in ALL_CASES]


def report(outcomes: list[Outcome], failures_only: bool = False) -> int:
    by_category: dict[str, list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        by_category[outcome.case.category].append(outcome)

    failures = [o for o in outcomes if not o.correct]

    if not failures_only:
        print("=" * 84)
        print("PHASE 11 EVALUATION - synthetic corpus, no model calls")
        print("=" * 84)
        for category in sorted(by_category):
            results = by_category[category]
            good = sum(1 for o in results if o.correct)
            gaps = sum(1 for o in results if not o.correct and o.case.known_gap)
            flag = "" if good == len(results) else f"   <-- {len(results) - good} failing"
            gap_note = f" ({gaps} known gap)" if gaps else ""
            print(f"\n{category:22s} {good}/{len(results)}{gap_note}{flag}")
            for outcome in results:
                mark = "PASS" if outcome.correct else "FAIL"
                gap = " [known gap]" if not outcome.correct and outcome.case.known_gap else ""
                print(f"   {mark}  {outcome.case.id:34s} -> {outcome.status}{gap}")

    print("\n" + "=" * 84)
    print("FAILURES IN DETAIL")
    print("=" * 84)
    if not failures:
        print("  (none)")
    for outcome in failures:
        case = outcome.case
        print(f"\n[{outcome.error_type}] {case.id}  ({case.category})")
        print(f"  known gap : {'yes' if case.known_gap else 'NO - unexpected'}")
        print(f"  document  : {case.page_text[:88]}")
        print(f"  answer    : {case.answer[:88]}")
        print(f"  quote     : {case.quote[:88]}")
        print(f"  expected  : {'released' if case.should_release else 'withheld'}")
        print(f"  actual    : {outcome.status} ({'released' if outcome.released else 'withheld'})")
        print(f"  reason    : {outcome.reason}")
        if case.notes:
            print(f"  note      : {case.notes}")

    attacks = [o for o in outcomes if o.case.family == "attack"]
    legit = [o for o in outcomes if o.case.family == "legitimate"]
    false_negatives = [o for o in attacks if not o.correct]
    false_positives = [o for o in legit if not o.correct]
    fn_known = sum(1 for o in false_negatives if o.case.known_gap)

    print("\n" + "=" * 84)
    print("SUMMARY")
    print("-" * 84)
    print(f"  Total adversarial cases            {len(attacks)}")
    print(f"  Detected attacks                   {len(attacks) - len(false_negatives)}")
    print(f"  Missed attacks (false negatives)   {len(false_negatives)}"
          f"   ({fn_known} in categories documented as unsupported)")
    print(f"  Total legitimate cases             {len(legit)}")
    print(f"  Correctly released                 {len(legit) - len(false_positives)}")
    print(f"  Incorrectly withheld (false pos.)  {len(false_positives)}")
    print("-" * 84)
    fn_rate = len(false_negatives) / len(attacks) if attacks else 0
    fp_rate = len(false_positives) / len(legit) if legit else 0
    print(f"  False-negative rate                {fn_rate:.1%}  ({len(false_negatives)}/{len(attacks)})")
    print(f"  False-positive rate                {fp_rate:.1%}  ({len(false_positives)}/{len(legit)})")
    print("=" * 84)
    print("\nSynthetic corpus. These rates describe behaviour on hand-written cases")
    print("chosen to probe known and suspected weaknesses - they are not a general")
    print("accuracy measurement, and no model was called.")

    return 1 if false_positives else 0


def threshold_sweep() -> None:
    """Re-run the corpus at several overlap thresholds.

    The threshold decides whether a polarity or modality difference counts as
    contradicting the evidence or merely as unsupported by it. Both outcomes
    withhold the claim, so the sweep shows how much of the corpus is actually
    sensitive to the value - which is the question worth answering before
    tuning it.
    """
    from app.verification import semantics

    original = semantics.SAME_STATEMENT_OVERLAP
    print("=" * 84)
    print("OVERLAP THRESHOLD SWEEP")
    print("=" * 84)
    print(f"{'threshold':>10}  {'attacks held':>13}  {'legit released':>15}  "
          f"{'false neg':>10}  {'false pos':>10}")
    print("-" * 84)

    baseline: dict[str, str] | None = None
    for value in (0.4, 0.5, 0.6, 0.7, 0.8):
        semantics.SAME_STATEMENT_OVERLAP = value
        outcomes = run_all()
        attacks = [o for o in outcomes if o.case.family == "attack"]
        legit = [o for o in outcomes if o.case.family == "legitimate"]
        fn = sum(1 for o in attacks if not o.correct)
        fp = sum(1 for o in legit if not o.correct)
        marker = " <- current" if value == original else ""
        print(f"{value:>10.1f}  {len(attacks) - fn:>13}  {len(legit) - fp:>15}  "
              f"{fn:>10}  {fp:>10}{marker}")

        current = {o.case.id: o.status for o in outcomes}
        if baseline is None:
            baseline = current
        else:
            changed = [cid for cid, status in current.items() if baseline[cid] != status]
            if changed:
                print(f"{'':>10}  status changed vs 0.4: {', '.join(changed)}")
            baseline = current

    semantics.SAME_STATEMENT_OVERLAP = original
    print("-" * 84)
    print("A row that matches its neighbours means no case in the corpus is")
    print("sensitive to the threshold at that point.")
    print("=" * 84)


def _measure(name: str, provenance: str, cases, page_of, claim_of, quote_of,
             leak_of, contain_of) -> tuple[int, int, int, int]:
    """Score one corpus. Corpora are never averaged together."""
    false_negatives: list[str] = []
    false_positives: list[str] = []

    for case in cases:
        document = Document({1: page_of(case)})
        answer = ModelAnswer.model_validate(
            {
                "answer": claim_of(case),
                "evidence": [{"page": 1, "quote": quote_of(case)}],
                "not_found": False,
            }
        )
        response = gate_answer(
            document_id="doc_eval",
            question="What does the document say?",
            answer=answer,
            verified=verify_answer(answer, document),
            document=document,
        )
        released = "couldn't find" not in response.answer
        body = str(response.model_dump())
        leaked = [f for f in leak_of(case) if f in body]
        missing = [f for f in contain_of(case) if f not in response.answer]

        if case.family == "attack":
            if (released and response.answer == claim_of(case)) or leaked:
                false_negatives.append(case.id)
        elif not released or missing:
            false_positives.append(f"{case.id} ({response.status})")

    attacks = sum(1 for c in cases if c.family == "attack")
    legit = len(cases) - attacks
    print(f"\n{name}")
    print(f"  provenance: {provenance}")
    if attacks:
        rate = len(false_negatives) / attacks
        print(f"  attacks {attacks:3d}   detected {attacks - len(false_negatives):3d}   "
              f"missed {len(false_negatives):2d}   false-negative rate {rate:.1%}")
    if legit:
        rate = len(false_positives) / legit
        print(f"  legit   {legit:3d}   released {legit - len(false_positives):3d}   "
              f"withheld {len(false_positives):2d}   false-positive rate {rate:.1%}")
    if false_negatives:
        print(f"  missed attacks    : {', '.join(false_negatives)}")
    if false_positives:
        print(f"  withheld legitimate: {', '.join(false_positives)}")
    return attacks, len(false_negatives), legit, len(false_positives)


def corpora_report() -> int:
    """Every corpus, reported on its own terms.

    Kept separate deliberately. Averaging a corpus written by the people who
    wrote the checks with one drawn from real contract text would hide exactly
    the difference the second corpus exists to show.
    """
    from tests.fixtures_contracts import CONTRACT_ALL, DOCUMENT_FAMILIES
    from tests.fixtures_definitions import DEFINITION_ALL
    from tests.fixtures_entities import ENTITY_ALL
    from tests.fixtures_realistic import REALISTIC_ALL
    from tests.fixtures_roles import ROLE_ALL

    print("=" * 84)
    print("PHASE 13 - CORPORA REPORTED SEPARATELY (no model calls)")
    print("=" * 84)

    _measure(
        "REALISTIC / FAR - real public-domain contract text",
        "verbatim FAR clauses, acquisition.gov, US Government work (17 USC 105)",
        REALISTIC_ALL,
        lambda c: c.source_text, lambda c: c.claim, lambda c: c.quote,
        lambda c: c.must_not_leak, lambda c: c.must_contain,
    )
    _measure(
        "REALISTIC / CROSS-DOMAIN - real SaaS, employment, lease and DPA text",
        "SEC EDGAR exhibits and EU Decision 2021/914; 4 families, 4 jurisdictions",
        CONTRACT_ALL,
        lambda c: c.source_text, lambda c: c.claim, lambda c: c.quote,
        lambda c: c.must_not_leak, lambda c: c.must_contain,
    )
    # Per family as well as in total. A single figure across four contract
    # types would hide a family that fails completely.
    for family in DOCUMENT_FAMILIES:
        cases = [c for c in CONTRACT_ALL if c.document_family == family]
        _measure(
            f"    ...{family}",
            f"subset of the cross-domain corpus, {cases[0].jurisdiction}",
            cases,
            lambda c: c.source_text, lambda c: c.claim, lambda c: c.quote,
            lambda c: c.must_not_leak, lambda c: c.must_contain,
        )
    _measure(
        "NAMED ENTITY - synthetic, Phase 13",
        "written for this suite; the matrix behind the Phase 12 open gap",
        ENTITY_ALL,
        lambda c: c.evidence, lambda c: c.claim, lambda c: c.evidence,
        lambda c: (), lambda c: (),
    )
    _measure(
        "DEFINITIONS & CROSS-REFERENCES - mixed real and synthetic",
        "lease and EU SCC text where marked real; the rest written for this suite",
        DEFINITION_ALL,
        lambda c: c.page_text, lambda c: c.claim, lambda c: c.quote,
        lambda c: c.must_not_leak, lambda c: c.must_contain,
    )
    _measure(
        "ROLE REVERSAL - synthetic, Phase 12",
        "written for this suite; isolates the Phase 11 open gap",
        ROLE_ALL,
        lambda c: c.evidence, lambda c: c.claim, lambda c: c.evidence,
        lambda c: (), lambda c: (),
    )
    _measure(
        "SEMANTIC - synthetic, Phase 11",
        "written for this suite, alongside the checks it measures",
        ALL_CASES,
        lambda c: c.page_text, lambda c: c.answer, lambda c: c.quote,
        lambda c: c.must_not_leak, lambda c: c.must_contain,
    )

    print("\n" + "=" * 84)
    print("Only the two REALISTIC corpora use language nobody on this project")
    print("wrote. Their adversarial cases are still transformations WE applied to")
    print("that language, and are not naturally occurring text. The synthetic")
    print("figures are optimistic by construction and are not independent")
    print("validation. No model was called for any of these, so none of it")
    print("measures Nemotron's accuracy - only the application's grounding")
    print("boundary. Corpora are never averaged together.")
    print("=" * 84)
    return 0


def main() -> int:
    if "--threshold" in sys.argv:
        threshold_sweep()
        return 0
    if "--corpora" in sys.argv:
        return corpora_report()
    return report(run_all(), failures_only="--failures" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
