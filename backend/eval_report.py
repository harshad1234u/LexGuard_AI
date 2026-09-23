"""Deterministic grounding evaluation.

Runs the Phase 10 adversarial corpus through the real verification stack and
reports what actually happened. Every number printed is computed here, from
executed cases - nothing is asserted or carried over from a previous run.

    .venv/Scripts/python eval_report.py

This is NOT a benchmark of Nemotron. No model is called. The "model answers" in
the corpus are hand-written stand-ins, so what is measured is the
application's grounding boundary: given output a model could plausibly produce,
does the application release it or withhold it?

Both directions are reported. Refusing every answer would score 100% on the
attack half and 0% on the legitimate half, so a verifier is only working if
both columns are high.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.schemas.findings import ModelAnswer
from app.verification.qa import gate_answer, verify_answer
from tests.fixtures_adversarial import ATTACKS, LEGITIMATE


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


def run(case):
    document = Document({1: case.page_text})
    evidence = (
        [{"page": getattr(case, "page", 1), "quote": case.quote}] if case.quote else []
    )
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


def main() -> int:
    by_category: dict[str, list[bool]] = defaultdict(list)
    failures: list[str] = []

    print("=" * 78)
    print("GROUNDING EVALUATION - deterministic, no model calls")
    print("=" * 78)

    print("\nATTACKS - the model's wording must not be released as stated")
    print("-" * 78)
    for case in ATTACKS:
        response = run(case)
        status_ok = str(response.status) in case.allowed_statuses
        withheld_ok = (not case.must_withhold_answer) or response.answer != case.answer
        body = str(response.model_dump())
        leak_ok = all(fragment not in body for fragment in case.must_not_leak)
        passed = status_ok and withheld_ok and leak_ok

        by_category[case.category].append(passed)
        if not passed:
            failures.append(case.id)
        print(f"  {'PASS' if passed else 'FAIL'}  {case.id:34s} -> {response.status}")

    print("\nLEGITIMATE - correct answers must survive")
    print("-" * 78)
    legit: list[bool] = []
    for case in LEGITIMATE:
        response = run(case)
        passed = (
            str(response.status) in case.allowed_statuses
            and "couldn't find" not in response.answer
            and all(fragment in response.answer for fragment in case.must_contain)
        )
        legit.append(passed)
        if not passed:
            failures.append(case.id)
        print(f"  {'PASS' if passed else 'FAIL'}  {case.id:34s} -> {response.status}")

    print("\n" + "=" * 78)
    print("BY CATEGORY (attacks)")
    print("-" * 78)
    for category in sorted(by_category):
        results = by_category[category]
        print(f"  {category:18s} {sum(results)}/{len(results)} withheld correctly")

    attacks_passed = sum(sum(v) for v in by_category.values())
    attacks_total = sum(len(v) for v in by_category.values())

    print("-" * 78)
    print(f"  ATTACKS WITHHELD    {attacks_passed}/{attacks_total}")
    print(f"  LEGITIMATE RELEASED {sum(legit)}/{len(legit)}")
    print("=" * 78)

    if failures:
        print("\nFAILING CASES: " + ", ".join(failures))
        return 1

    print("\nNote: these figures describe the application's grounding boundary")
    print("against hand-written model output. They are not a measurement of any")
    print("model's accuracy, and no live model was called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
