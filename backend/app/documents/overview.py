"""Released findings, grouped by document topic.

This module is a PROJECTION. Its only input is `AnalysisResult.findings` -
the list the output safety policy already decided to publish - and every field
it emits is copied from that list verbatim:

    model proposal
        -> deterministic evidence verification
        -> claim-level semantic verification
        -> output safety policy          <- the release decision happens here
        -> AnalysisResult.findings
        -> THIS MODULE                   <- grouping only, nothing else
        -> API

Nothing here calls a provider, reads raw model output, reads a withheld
finding, or produces a claim. A withheld finding is not merely filtered out:
`AnalysisResult` carries withheld findings as counts and never as content, so
the material is not reachable from this module's input at all. That is the
strongest form the safety property can take, and a test asserts it.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
The distinction that governs every wording choice below:

    "these verified findings are about termination"   is navigation
    "this contract has no termination clause"         is a conclusion

The first is what this module produces. The second is a statement of absence,
and the application is not in a position to make it: it knows what survived
verification, not what the document contains. An empty topic therefore says
that nothing was released for it, never that the document is silent on it -
the same distinction `values.py` keeps between "no values detected" and "no
text was read", and for the same reason.

It is also not a summary. A summary is a claim spanning a document, and the
verifier binds a claim to the sentence its evidence sits in. This adds no
claim of any kind; it puts existing ones under headings.
"""

from __future__ import annotations

import re

from app.schemas.analysis import (
    AnalysisResult,
    DocumentOverview,
    OverviewCategory,
    OverviewCategoryGroup,
    OverviewItem,
)

#: Display heading for each topic. Application-chosen, never model text.
CATEGORY_LABELS: dict[OverviewCategory, str] = {
    OverviewCategory.PARTIES: "Parties and roles",
    OverviewCategory.FEES: "Fees and payments",
    OverviewCategory.TERM: "Term and renewal",
    OverviewCategory.TERMINATION: "Termination",
    OverviewCategory.CONFIDENTIALITY: "Confidentiality",
    OverviewCategory.LIABILITY: "Liability",
    OverviewCategory.NOTICES: "Notices",
    OverviewCategory.GOVERNING_LAW: "Governing law",
    OverviewCategory.OTHER: "Other clauses",
}

#: The order topics are published in. Roughly the order a contract introduces
#: them, so the overview reads like the document rather than like a hash map.
#: `OTHER` is last because it is a remainder, not a topic.
CATEGORY_ORDER: tuple[OverviewCategory, ...] = (
    OverviewCategory.PARTIES,
    OverviewCategory.TERM,
    OverviewCategory.FEES,
    OverviewCategory.TERMINATION,
    OverviewCategory.CONFIDENTIALITY,
    OverviewCategory.LIABILITY,
    OverviewCategory.NOTICES,
    OverviewCategory.GOVERNING_LAW,
    OverviewCategory.OTHER,
)

#: Topics always published, empty or not.
#:
#: `OTHER` is excluded: it is a remainder rather than a topic, and "no verified
#: finding was released for Other clauses" tells a reader nothing. It appears
#: only when something landed in it.
ALWAYS_SHOWN: tuple[OverviewCategory, ...] = tuple(
    category for category in CATEGORY_ORDER if category is not OverviewCategory.OTHER
)

#: What an empty topic says.
#:
#: Every word here is load-bearing. "Released" names the application's own
#: decision; "for this category" scopes it to the grouping. It does not say
#: missing, absent, not present, not included, incomplete or deficient, none of
#: which the application can establish. The counts published beside it let a
#: reader see how much was proposed and how much was withheld.
EMPTY_MESSAGE = "No verified finding was released for this category."

#: Vocabulary that maps a finding's own `type` onto a topic.
#:
#: Closed by construction: the lookup can only ever return a member of
#: `OverviewCategory`, so no model-supplied string can create a heading. The
#: keys cover the categories `prompts.py` suggests to the model, plus the
#: ordinary synonyms a model reaches for when left to choose freely - "fees"
#: and "payment" for the same clause, "term" and "duration", "governing_law"
#: and "jurisdiction".
#:
#: Matching is on whole words only (see `categorise`). Substring matching would
#: put "non-payment of liability insurance" under Fees on the strength of four
#: letters, and would let a longer label drift into a topic it is not about.
_KEYWORDS: dict[str, OverviewCategory] = {
    # Parties and roles
    "parties": OverviewCategory.PARTIES,
    "party": OverviewCategory.PARTIES,
    "roles": OverviewCategory.PARTIES,
    "role": OverviewCategory.PARTIES,
    "appointment": OverviewCategory.PARTIES,
    "engagement": OverviewCategory.PARTIES,
    # Term and renewal
    "term": OverviewCategory.TERM,
    "duration": OverviewCategory.TERM,
    "renewal": OverviewCategory.TERM,
    "renew": OverviewCategory.TERM,
    "commencement": OverviewCategory.TERM,
    "expiry": OverviewCategory.TERM,
    "expiration": OverviewCategory.TERM,
    # Fees and payments
    "fees": OverviewCategory.FEES,
    "fee": OverviewCategory.FEES,
    "payment": OverviewCategory.FEES,
    "payments": OverviewCategory.FEES,
    "price": OverviewCategory.FEES,
    "pricing": OverviewCategory.FEES,
    "invoice": OverviewCategory.FEES,
    "invoicing": OverviewCategory.FEES,
    "charges": OverviewCategory.FEES,
    "remuneration": OverviewCategory.FEES,
    "expenses": OverviewCategory.FEES,
    "interest": OverviewCategory.FEES,
    # Termination
    "termination": OverviewCategory.TERMINATION,
    "terminate": OverviewCategory.TERMINATION,
    "cancellation": OverviewCategory.TERMINATION,
    "breach": OverviewCategory.TERMINATION,
    "default": OverviewCategory.TERMINATION,
    # Confidentiality
    "confidentiality": OverviewCategory.CONFIDENTIALITY,
    "confidential": OverviewCategory.CONFIDENTIALITY,
    "nondisclosure": OverviewCategory.CONFIDENTIALITY,
    "secrecy": OverviewCategory.CONFIDENTIALITY,
    "privacy": OverviewCategory.CONFIDENTIALITY,
    "data": OverviewCategory.CONFIDENTIALITY,
    # Liability
    "liability": OverviewCategory.LIABILITY,
    "liabilities": OverviewCategory.LIABILITY,
    "indemnity": OverviewCategory.LIABILITY,
    "indemnification": OverviewCategory.LIABILITY,
    "indemnities": OverviewCategory.LIABILITY,
    "warranty": OverviewCategory.LIABILITY,
    "warranties": OverviewCategory.LIABILITY,
    "insurance": OverviewCategory.LIABILITY,
    # Notices
    "notices": OverviewCategory.NOTICES,
    "notice": OverviewCategory.NOTICES,
    "communications": OverviewCategory.NOTICES,
    # Governing law
    "governing": OverviewCategory.GOVERNING_LAW,
    "jurisdiction": OverviewCategory.GOVERNING_LAW,
    "arbitration": OverviewCategory.GOVERNING_LAW,
    "disputes": OverviewCategory.GOVERNING_LAW,
    "dispute": OverviewCategory.GOVERNING_LAW,
    "venue": OverviewCategory.GOVERNING_LAW,
}

#: Multi-word labels that are one topic even though their words disagree.
#: Checked before the word lookup, because "governing law" would otherwise be
#: settled by whichever of its two words the iteration reached first.
_PHRASES: tuple[tuple[str, OverviewCategory], ...] = (
    ("governing law", OverviewCategory.GOVERNING_LAW),
    ("applicable law", OverviewCategory.GOVERNING_LAW),
    ("dispute resolution", OverviewCategory.GOVERNING_LAW),
    ("limitation of liability", OverviewCategory.LIABILITY),
    ("intellectual property", OverviewCategory.OTHER),
    ("force majeure", OverviewCategory.OTHER),
    ("term and renewal", OverviewCategory.TERM),
    ("payment terms", OverviewCategory.FEES),
)

_WORD = re.compile(r"[a-z]+")

#: The longest label this module will read. `safe_type` already bounds the
#: published label to 40 characters; this is a second, independent bound so a
#: change there cannot hand this module an unbounded string to scan.
_MAX_LABEL_CHARS = 64


def _normalise(label: str) -> str:
    """A label reduced to lowercase words, for lookup only.

    Never published - the finding's own label is published as the finding
    carries it. This is scanning input, and it is bounded before it is scanned.
    """
    return " ".join(_WORD.findall(str(label or "").casefold()[:_MAX_LABEL_CHARS]))


def categorise(label: str) -> OverviewCategory:
    """Map a finding's own category label onto one published topic.

    Total by construction: every input returns a member of `OverviewCategory`,
    and an unrecognised label returns `OTHER`. There is no path by which a
    model-chosen string becomes a heading, however it is spelled - which is
    what makes an injection-shaped label harmless here rather than merely
    unlikely. It has already been refused upstream by `safe_type`; this is the
    second of the two independent reasons it cannot matter.

    Word-boundary matching, not substring: "non-payment" is about payment,
    "counterparty" is not about parties.
    """
    text = _normalise(label)
    if not text:
        return OverviewCategory.OTHER

    for phrase, category in _PHRASES:
        if phrase in text:
            return category

    for word in text.split():
        category = _KEYWORDS.get(word)
        if category is not None:
            return category

    return OverviewCategory.OTHER


def build_overview(result: AnalysisResult | None) -> DocumentOverview:
    """Group a gated analysis result by topic.

    `result` is the object the output policy produced. A missing result - a
    state that never reached the gate - yields an empty overview rather than a
    guess, matching `build_result`'s own fail-closed behaviour.

    Every published field is copied from a finding in `result.findings`. The
    counts are the ones that result already carries, so the overview and the
    findings list cannot disagree about how much was withheld.
    """
    if result is None:
        return DocumentOverview()

    grouped: dict[OverviewCategory, list[OverviewItem]] = {}
    for finding in result.findings:
        # Copied, never reconstructed. `section` is already confirmed-or-None
        # by the release policy, and is carried through in whichever state it
        # arrived in.
        item = OverviewItem(
            finding_id=finding.id,
            claim=finding.claim,
            quote=finding.evidence.quote,
            page=finding.evidence.page,
            section=finding.evidence.section,
            label=finding.type,
        )
        grouped.setdefault(categorise(finding.type), []).append(item)

    categories: list[OverviewCategoryGroup] = []
    for category in CATEGORY_ORDER:
        items = grouped.get(category, [])
        if not items and category not in ALWAYS_SHOWN:
            continue
        categories.append(
            OverviewCategoryGroup(
                key=category,
                label=CATEGORY_LABELS[category],
                items=items,
                # A topic with items needs no message, and an empty one gets
                # the message rather than any text derived from a finding.
                empty_message=None if items else EMPTY_MESSAGE,
            )
        )

    return DocumentOverview(
        categories=categories,
        released_count=len(result.findings),
        proposed_count=result.proposed_count,
        withheld_count=result.withheld.total,
    )
