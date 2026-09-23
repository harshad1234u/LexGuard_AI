"""Phase 12 experiment: is grammatical role binding worth a new dependency?

NOT production code. Nothing in `app/` imports this. It exists to answer one
question with measurements instead of intuition:

    does binding parties to grammatical roles detect enough reversals, without
    destroying enough legitimate paraphrases, to justify adding an NLP
    dependency to a project that currently has none?

Three approaches are compared on the same corpus:

    A  current   - party-presence check, as shipped
    B  heuristic - deterministic role binding from surface patterns, no deps
    C  parser    - spaCy dependency parse, if it happens to be installed

Run:

    .venv/Scripts/python experiments/role_binding.py

The corpus is deliberately stocked with voice changes and single-party clauses,
because the interesting failure is not "does it catch reversals" - a checker
that flags everything catches them all - but "does it leave faithful
paraphrases alone".
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.verification.semantics import PARTY_ALIASES, parties_in  # noqa: E402
from tests.fixtures_roles import ROLE_ALL, RoleCase  # noqa: E402

# ---------------------------------------------------------------------------
# Approach A - what ships today
# ---------------------------------------------------------------------------


def approach_a(case: RoleCase) -> bool:
    """True = flags the claim as a role problem.

    The current rule: every party named in the claim must appear in the
    evidence. Blind to reversal whenever both parties appear in both.
    """
    claim_parties = parties_in(case.claim)
    return bool(claim_parties) and not claim_parties <= parties_in(case.evidence)


# ---------------------------------------------------------------------------
# Approach B - deterministic role binding, no dependency
# ---------------------------------------------------------------------------

_PARTY_RE = re.compile(
    r"\b(?:the\s+)?((?:[A-Z][A-Za-z]*\s+)*(?:Party|Parties|Customer|Client|Supplier|"
    r"Vendor|Contractor|Subcontractor|Employee|Employer|Landlord|Tenant|Licensor|"
    r"Licensee|Buyer|Seller|Purchaser|Provider|Recipient|Discloser|Lessor|Lessee|"
    r"Consultant|Agent|Borrower|Lender|Company|Processor|Controller|Government|"
    r"Ltd|Inc|LLC|Corp))\b"
)

_PASSIVE_AGENT = re.compile(r"\bby\s+(?:the\s+)?([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*)\b")


#: Corporate suffixes carry no identity: "ABC Ltd" and "XYZ Ltd" share a head
#: noun and are different parties. For those the distinguishing token is the
#: name in front of the suffix, not the suffix itself.
_SUFFIXES = {"ltd", "inc", "llc", "corp", "plc", "gmbh"}


def _normalise(term: str) -> str:
    words = term.strip().split()
    head = words[-1].lower()
    if head in _SUFFIXES and len(words) > 1:
        return " ".join(w.lower() for w in words)
    return PARTY_ALIASES.get(head, head)


def _actor_of(sentence: str) -> str | None:
    """Who performs the action, under a small set of surface patterns.

    Two shapes cover most contractual drafting:

        active   "The Supplier shall deliver ..."   -> first party before the verb
        passive  "... shall be delivered by the Supplier" -> the `by` agent

    Passive is checked first: in "The goods shall be delivered by the Supplier"
    the first party-like token is the agent only if you read `by`, which is
    exactly the case a word-order rule gets wrong.
    """
    passive = _PASSIVE_AGENT.search(sentence)
    if passive and re.search(r"\b(?:be|been)\s+\w+ed\b", sentence, re.IGNORECASE):
        return _normalise(passive.group(1))

    match = _PARTY_RE.search(sentence)
    return _normalise(match.group(1)) if match else None


def approach_b(case: RoleCase) -> bool:
    """Flag when the acting party differs between evidence and claim."""
    evidence_actor = _actor_of(case.evidence)
    claim_actor = _actor_of(case.claim)

    # No actor identified on either side: nothing to compare, stay silent.
    if evidence_actor is None or claim_actor is None:
        return False
    return evidence_actor != claim_actor


# ---------------------------------------------------------------------------
# Approach C - dependency parse, only if spaCy is already present
# ---------------------------------------------------------------------------

_NLP = None
_SPACY_STATUS = "not installed"


def _load_spacy():
    global _NLP, _SPACY_STATUS
    if _NLP is not None:
        return _NLP
    try:
        import spacy
    except ImportError:
        _SPACY_STATUS = "not installed"
        return None
    try:
        _NLP = spacy.load("en_core_web_sm")
        _SPACY_STATUS = f"spacy {spacy.__version__} + en_core_web_sm"
    except OSError:
        _SPACY_STATUS = "spacy installed, model en_core_web_sm missing"
        return None
    return _NLP


def _spacy_actor(sentence: str) -> str | None:
    nlp = _load_spacy()
    if nlp is None:
        return None
    doc = nlp(sentence)
    for token in doc:
        if token.dep_ == "nsubjpass":
            for child in token.head.children:
                if child.dep_ == "agent":
                    for obj in child.children:
                        if obj.dep_ == "pobj":
                            return _normalise(obj.text)
        if token.dep_ == "nsubj":
            return _normalise(token.text)
    return None


def approach_c(case: RoleCase) -> bool | None:
    if _load_spacy() is None:
        return None
    evidence_actor = _spacy_actor(case.evidence)
    claim_actor = _spacy_actor(case.claim)
    if evidence_actor is None or claim_actor is None:
        return False
    return evidence_actor != claim_actor


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def score(name: str, fn, cases: list[RoleCase]):
    detected = missed = preserved = destroyed = 0
    unavailable = False
    failures: list[str] = []

    started = time.perf_counter()
    for case in cases:
        flagged = fn(case)
        if flagged is None:
            unavailable = True
            break
        if case.family == "attack":
            if flagged:
                detected += 1
            else:
                missed += 1
                failures.append(f"missed {case.id}")
        else:
            if flagged:
                destroyed += 1
                failures.append(f"FALSE POSITIVE {case.id}")
            else:
                preserved += 1
    elapsed = (time.perf_counter() - started) * 1000

    if unavailable:
        print(f"\n{name}\n  UNAVAILABLE - {_SPACY_STATUS}")
        return None

    attacks = sum(1 for c in cases if c.family == "attack")
    legit = len(cases) - attacks
    print(f"\n{name}")
    print(f"  reversals detected      {detected}/{attacks}")
    print(f"  reversals missed        {missed}")
    print(f"  legitimate preserved    {preserved}/{legit}")
    print(f"  legitimate destroyed    {destroyed}   <-- false positives")
    print(f"  time for {len(cases)} cases     {elapsed:.1f} ms")
    if failures:
        print(f"  failures: {', '.join(failures)}")
    return detected, missed, preserved, destroyed, elapsed


def main() -> int:
    print("=" * 78)
    print("ROLE-BINDING EXPERIMENT - not production code")
    print("=" * 78)
    attacks = sum(1 for c in ROLE_ALL if c.family == "attack")
    print(f"corpus: {len(ROLE_ALL)} cases ({attacks} reversals, "
          f"{len(ROLE_ALL) - attacks} legitimate)")

    score("A  current party-presence check (shipped)", approach_a, ROLE_ALL)
    score("B  deterministic role binding (no dependency)", approach_b, ROLE_ALL)
    score("C  spaCy dependency parse", approach_c, ROLE_ALL)

    print("\n" + "=" * 78)
    print("By construction (approach B):")
    print("-" * 78)
    groups: dict[str, list[RoleCase]] = {}
    for case in ROLE_ALL:
        groups.setdefault(case.construction, []).append(case)
    for construction, cases in sorted(groups.items()):
        correct = sum(
            1 for c in cases if approach_b(c) == (c.family == "attack")
        )
        print(f"  {construction:24s} {correct}/{len(cases)}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
