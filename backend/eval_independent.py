"""Phase 14: the independent corpus and mutation-style validation.

    .venv/Scripts/python eval_independent.py              corpus, per family
    .venv/Scripts/python eval_independent.py --failures   only what failed
    .venv/Scripts/python eval_independent.py --mutations  mutation coverage
    .venv/Scripts/python eval_independent.py --findings   the analysis path

Two things this reports that `eval_harness.py` does not:

1. **Scoring is stricter.** The older harness counts an attack as detected when
   the model's wording does not come back *verbatim*. Claim-level splitting
   makes that too generous: drop one sentence of a two-sentence answer and the
   string no longer matches, while the fabricated sentence still reached the
   user. Here an attack is detected only when none of the forbidden content
   appears anywhere in the response.

2. **Both surfaces.** Q&A and the analysis findings path are scored
   separately, because until Phase 14 they did not run the same checks and a
   figure measured on one said nothing about the other.

No model is called. These figures describe the application's grounding
boundary against written cases, not Nemotron's accuracy.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict

from app.schemas.findings import Evidence, Finding, ModelAnalysis, ModelAnswer
from app.verification.findings import verify_analysis_claims
from app.verification.qa import gate_answer, verify_answer
from tests.fixtures_independent import (
    INDEPENDENT_ALL,
    INDEPENDENT_LEGITIMATE,
    IndependentCase,
)


class Document:
    def __init__(self, pages: dict[int, str | None]):
        self._pages = pages
        self.page_count = len(pages)

    def page_text(self, page_number: int) -> str | None:
        return self._pages.get(page_number)


# ---------------------------------------------------------------------------
# Q&A path
# ---------------------------------------------------------------------------


class Result:
    """What happened to one case, and whether that was the right thing."""

    __slots__ = ("case", "status", "answer", "released", "correct", "reason")

    def __init__(self, case: IndependentCase, response):
        self.case = case
        self.status = str(response.status)
        self.answer = response.answer
        self.released = "couldn't find" not in response.answer

        body = str(response.model_dump())
        leaked = [f for f in case.must_not_leak if f in body]
        missing = [f for f in case.must_contain if f not in response.answer]
        claim_released = case.claim.strip() in self.answer

        if case.family in {"attack", "unresolved"}:
            self.correct = not leaked and not claim_released
            if leaked:
                self.reason = f"leaked {leaked!r}"
            elif claim_released:
                self.reason = "the manipulated statement reached the user"
            else:
                self.reason = ""
        elif case.family == "legitimate":
            self.correct = self.released and not missing
            if not self.released:
                self.reason = "a faithful answer was withheld entirely"
            elif missing:
                self.reason = f"dropped required content {missing!r}"
            else:
                self.reason = ""
        else:  # ambiguous - reported, never scored
            self.correct = True
            self.reason = ""

    @property
    def error_type(self) -> str:
        if self.correct:
            return ""
        return "FALSE NEGATIVE" if self.case.family != "legitimate" else "FALSE POSITIVE"


def run_qa(case: IndependentCase) -> Result:
    document = Document({1: case.page_text})
    answer = ModelAnswer(
        answer=case.claim,
        evidence=[Evidence(page=1, quote=case.quote)],
        not_found=False,
    )
    response = gate_answer(
        document_id="doc_independent",
        question="What does the document say about this?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )
    return Result(case, response)


# ---------------------------------------------------------------------------
# Analysis findings path
# ---------------------------------------------------------------------------


def run_findings(case: IndependentCase) -> tuple[IndependentCase, bool, str]:
    """Put the same case through the analysis path. Returns (case, shown, why)."""
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
    verified = verify_analysis_claims(analysis, document)
    item = verified[0]
    reasons = ",".join(str(r) for r in item.verification.reasons) or str(
        item.verification.status
    )
    return case, item.is_displayable_as_fact, reasons


def findings_report() -> int:
    shown_attacks: list[str] = []
    withheld_legit: list[str] = []

    for case in INDEPENDENT_ALL:
        _, shown, why = run_findings(case)
        if case.family in {"attack", "unresolved"} and shown:
            shown_attacks.append(case.id)
        elif case.family == "legitimate" and not shown:
            withheld_legit.append(f"{case.id} ({why})")

    attacks = [c for c in INDEPENDENT_ALL if c.family in {"attack", "unresolved"}]
    legit = list(INDEPENDENT_LEGITIMATE)

    print("=" * 84)
    print("ANALYSIS FINDINGS PATH - independent corpus")
    print("=" * 84)
    print(f"  adversarial/unresolved {len(attacks):3d}   withheld "
          f"{len(attacks) - len(shown_attacks):3d}   shown as verified {len(shown_attacks):2d}")
    print(f"  legitimate             {len(legit):3d}   shown    "
          f"{len(legit) - len(withheld_legit):3d}   withheld          {len(withheld_legit):2d}")
    if shown_attacks:
        print(f"  shown though adversarial: {', '.join(shown_attacks)}")
    if withheld_legit:
        print(f"  withheld though faithful: {', '.join(withheld_legit)}")
    print("=" * 84)
    return 0


# ---------------------------------------------------------------------------
# Corpus report
# ---------------------------------------------------------------------------


def corpus_report(failures_only: bool = False) -> int:
    results = [run_qa(case) for case in INDEPENDENT_ALL]

    by_family: dict[str, list[Result]] = defaultdict(list)
    by_category: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        by_family[result.case.contract_family].append(result)
        by_category[result.case.category].append(result)

    if not failures_only:
        print("=" * 84)
        print("PHASE 14 INDEPENDENT CORPUS - Q&A path, no model calls")
        print("=" * 84)

        print("\nBY CONTRACT FAMILY")
        print("-" * 84)
        for family in sorted(by_family):
            rows = by_family[family]
            _print_group(family, rows)

        print("\nBY ATTACK CATEGORY")
        print("-" * 84)
        for category in sorted(by_category):
            _print_group(category, by_category[category])

    failures = [r for r in results if not r.correct]
    print("\n" + "=" * 84)
    print("FAILURES IN DETAIL")
    print("=" * 84)
    if not failures:
        print("  (none)")
    for result in failures:
        case = result.case
        print(f"\n[{result.error_type}] {case.id}  ({case.contract_family}/{case.category})")
        print(f"  document : {case.page_text[:100]}")
        print(f"  claim    : {case.claim[:100]}")
        print(f"  quote    : {case.quote[:100]}")
        print(f"  outcome  : {result.status} ({'released' if result.released else 'withheld'})")
        print(f"  reason   : {result.reason}")
        print(f"  authored : {case.rationale[:160]}")

    _summary(results)
    return 0


def _print_group(name: str, rows: list[Result]) -> None:
    scored = [r for r in rows if r.case.is_scored]
    attacks = [r for r in scored if r.case.family in {"attack", "unresolved"}]
    legit = [r for r in scored if r.case.family == "legitimate"]
    ambiguous = [r for r in rows if not r.case.is_scored]
    detected = sum(1 for r in attacks if r.correct)
    released = sum(1 for r in legit if r.correct)
    note = f"   ambiguous {len(ambiguous)}" if ambiguous else ""
    print(
        f"  {name:16s} attacks {detected:2d}/{len(attacks):<2d}   "
        f"legit {released:2d}/{len(legit):<2d}{note}"
    )


def _summary(results: list[Result]) -> None:
    scored = [r for r in results if r.case.is_scored]
    attacks = [r for r in scored if r.case.family in {"attack", "unresolved"}]
    legit = [r for r in scored if r.case.family == "legitimate"]
    ambiguous = [r for r in results if not r.case.is_scored]
    missed = [r for r in attacks if not r.correct]
    withheld = [r for r in legit if not r.correct]

    print("\n" + "=" * 84)
    print("SUMMARY - independent corpus")
    print("-" * 84)
    print(f"  Total cases                        {len(results)}")
    print(f"  Adversarial + unresolved           {len(attacks)}")
    print(f"  Detected                           {len(attacks) - len(missed)}")
    print(f"  Missed (false negatives)           {len(missed)}")
    print(f"  Legitimate                         {len(legit)}")
    print(f"  Correctly released                 {len(legit) - len(withheld)}")
    print(f"  Incorrectly withheld (false pos.)  {len(withheld)}")
    print(f"  Ambiguous (reported, not scored)   {len(ambiguous)}")
    print("-" * 84)
    if attacks:
        print(f"  Detection rate                     {(len(attacks) - len(missed)) / len(attacks):.1%}")
    if legit:
        print(f"  False-positive rate                {len(withheld) / len(legit):.1%}")
    print("=" * 84)
    print("\nWritten for this suite in four contract families' drafting styles, not")
    print("copied from real agreements. Independent of the checks, not of this")
    print("project. No model was called.")


# ---------------------------------------------------------------------------
# Mutation-style validation
# ---------------------------------------------------------------------------

#: One semantic property changed per mutation. Each is a (name, transform)
#: pair; a transform returns None when it does not apply to this sentence, so
#: "not applicable" is never silently counted as "detected".
def _mutate_polarity(text: str) -> str | None:
    for modal in ("shall", "must", "may", "will"):
        pattern = re.compile(rf"\b{modal}\b(?! not)", re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub(f"{modal} not", text, count=1)
    return None


def _mutate_modality(text: str) -> str | None:
    if re.search(r"\bshall\b", text, re.IGNORECASE):
        return re.sub(r"\bshall\b", "may", text, count=1, flags=re.IGNORECASE)
    if re.search(r"\bmay\b", text, re.IGNORECASE):
        return re.sub(r"\bmay\b", "shall", text, count=1, flags=re.IGNORECASE)
    return None


#: Role pairs whose swap inverts an obligation, one pair per contract family.
_ROLE_PAIRS = (
    ("Provider", "Payer"),
    ("Contractor", "Employer"),
    ("Insured", "Insurer"),
    ("Student", "Institution"),
    ("Contract Administrator", "Contractor"),
)


def _mutate_actor(text: str) -> str | None:
    for first, second in _ROLE_PAIRS:
        if first in text and second in text:
            swapped = text.replace(first, "\0").replace(second, first).replace("\0", second)
            return swapped if swapped != text else None
    for first, second in _ROLE_PAIRS:
        if first in text:
            return text.replace(first, second, 1)
    return None


def _mutate_quantity(text: str) -> str | None:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    raw = match.group(0)
    digits = raw.replace(",", "").replace(".", "")
    if not digits.isdigit():
        return None
    # A different figure of the same shape, so only the value changes.
    bumped = str(int(digits) + 1)
    return text[: match.start()] + bumped + text[match.end() :]


def _mutate_currency(text: str) -> str | None:
    for symbol, other in (("£", "$"), ("$", "£"), ("Rs ", "$"), ("€", "$")):
        if symbol in text:
            return text.replace(symbol, other, 1)
    return None


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _mutate_date(text: str) -> str | None:
    for index, month in enumerate(_MONTHS):
        if month in text:
            return text.replace(month, _MONTHS[(index + 1) % 12], 1)
    return None


def _mutate_remove_condition(text: str) -> str | None:
    match = re.match(r"^(If|Where|Unless|Provided that|Subject to)\b[^,]*,\s*", text)
    if match:
        remainder = text[match.end() :]
        return remainder[:1].upper() + remainder[1:]
    return None


def _mutate_remove_exception(text: str) -> str | None:
    pattern = re.compile(r",\s*(other than|except|excluding|save for|unless)\b[^.]*")
    if pattern.search(text):
        return pattern.sub("", text, count=1)
    return None


def _mutate_broaden_scope(text: str) -> str | None:
    if re.search(r"\bonly\b", text, re.IGNORECASE):
        return re.sub(r"\bonly\s*", "", text, count=1, flags=re.IGNORECASE)
    if re.search(r"\bnot less than\b", text, re.IGNORECASE):
        return re.sub(r"\bnot less than\s*", "", text, count=1, flags=re.IGNORECASE)
    if re.search(r"\bup to\b", text, re.IGNORECASE):
        return re.sub(r"\bup to\s*", "", text, count=1, flags=re.IGNORECASE)
    return None


def _mutate_remove_limit(text: str) -> str | None:
    pattern = re.compile(r",?\s*(up to an aggregate maximum of|up to a maximum of)\b[^.]*")
    if pattern.search(text):
        return pattern.sub("", text, count=1)
    if re.search(r"\bwithin\b", text, re.IGNORECASE):
        return re.sub(r"\bwithin\b", "after", text, count=1, flags=re.IGNORECASE)
    return None


def _mutate_named_entity(text: str) -> str | None:
    match = re.search(r"\b(Annex|Schedule|Section|Clause|Appendix)\s+(\w+)", text)
    if match:
        return text[: match.start(2)] + "99" + text[match.end(2) :]
    return None


MUTATIONS = (
    ("polarity", _mutate_polarity),
    ("modality", _mutate_modality),
    ("actor", _mutate_actor),
    ("quantity", _mutate_quantity),
    ("currency", _mutate_currency),
    ("date", _mutate_date),
    ("condition_removed", _mutate_remove_condition),
    ("exception_removed", _mutate_remove_exception),
    ("scope_broadened", _mutate_broaden_scope),
    ("limit_removed", _mutate_remove_limit),
    ("cross_reference", _mutate_named_entity),
)


def mutate(case: IndependentCase, transform) -> tuple[str, bool] | None:
    """Apply one mutation to a legitimate claim and see whether it is caught.

    The evidence is left exactly as it was. Only the statement changes, which
    is the point: the document still says what it said, and the question is
    whether the application notices that the answer no longer does.
    """
    mutated = transform(case.claim)
    if mutated is None or mutated.strip() == case.claim.strip():
        return None

    document = Document({1: case.page_text})
    answer = ModelAnswer(
        answer=mutated, evidence=[Evidence(page=1, quote=case.quote)], not_found=False
    )
    response = gate_answer(
        document_id="doc_mutation",
        question="What does the document say about this?",
        answer=answer,
        verified=verify_answer(answer, document),
        document=document,
    )
    detected = mutated.strip() not in response.answer
    return mutated, detected


def mutation_report() -> int:
    by_kind: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)

    for case in INDEPENDENT_LEGITIMATE:
        for name, transform in MUTATIONS:
            outcome = mutate(case, transform)
            if outcome is None:
                continue
            mutated, detected = outcome
            by_kind[name].append((case.id, mutated, detected))

    print("=" * 84)
    print("MUTATION-STYLE VALIDATION - one semantic property changed at a time")
    print("=" * 84)
    print("Each mutation is applied to a claim this corpus says is faithful, with")
    print("the evidence left untouched. A mutation is 'detected' when the mutated")
    print("sentence does not reach the user.\n")

    total = detected_total = 0
    print(f"  {'mutation':20s} {'applied':>8s} {'detected':>9s} {'missed':>7s}")
    print("  " + "-" * 48)
    for name, _ in MUTATIONS:
        rows = by_kind.get(name, [])
        if not rows:
            print(f"  {name:20s} {'0':>8s} {'-':>9s} {'-':>7s}   (not applicable)")
            continue
        hits = sum(1 for _, _, ok in rows if ok)
        total += len(rows)
        detected_total += hits
        print(f"  {name:20s} {len(rows):>8d} {hits:>9d} {len(rows) - hits:>7d}")

    print("  " + "-" * 48)
    rate = detected_total / total if total else 0
    print(f"  {'TOTAL':20s} {total:>8d} {detected_total:>9d} {total - detected_total:>7d}"
          f"   {rate:.1%}")

    misses = [
        (name, case_id, mutated)
        for name, rows in by_kind.items()
        for case_id, mutated, ok in rows
        if not ok
    ]
    print("\n" + "=" * 84)
    print("MISSED MUTATIONS")
    print("=" * 84)
    if not misses:
        print("  (none)")
    for name, case_id, mutated in misses:
        print(f"\n  [{name}] {case_id}")
        print(f"    released: {mutated[:120]}")
    print("\n" + "=" * 84)
    print("Mutation coverage measures whether a change of meaning changes the")
    print("outcome. It says nothing about legal accuracy.")
    print("=" * 84)
    return 0


def main() -> int:
    if "--mutations" in sys.argv:
        return mutation_report()
    if "--findings" in sys.argv:
        return findings_report()
    return corpus_report(failures_only="--failures" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
