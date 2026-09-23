"""Evidence grounding - does the document actually say what the model claims?

This is the layer that decides whether a model's proposal may reach the user as
a fact. It is deterministic on purpose: asking a model to check its own evidence
would put the same fallible judgement on both sides of the question
(docs/02_ARCHITECTURE.md sec. 5.5).

The check chain, in order, matching docs/02_ARCHITECTURE.md sec. 9:

    evidence present? -> page exists? -> quote occurs there? -> values agree?

Each step can only lower the verdict. There is no path by which a later check
rescues an earlier failure.

Scope: this verifier answers "does this evidence occur in the source, and are
its critical values consistent?" It does not, and must not, attempt to decide
whether a claim is legally correct.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Protocol, runtime_checkable

from app.core.logging import get_logger
from app.schemas.findings import (
    Finding,
    ModelAnalysis,
    QuoteMatchType,
    VerificationReason,
    VerificationResult,
    VerificationStatus,
    VerifiedFinding,
)
from app.verification.numeric import Comparison, compare_numbers
from app.verification.text import is_blank, normalize

logger = get_logger(__name__)

#: Similarity required for a non-exact quote to count as found. High enough
#: that "30 days" and "60 days" (0.71) come nowhere near it.
NEAR_MATCH_THRESHOLD = 0.90

#: Quotes beyond this are not evidence, they are a paste of the page. Also
#: bounds the cost of fuzzy matching on hostile input.
MAX_QUOTE_CHARS = 2000


@runtime_checkable
class EvidenceSource(Protocol):
    """The document, as verification needs to see it.

    Deliberately minimal so the verifier depends on no storage detail;
    `DocumentRecord` satisfies it structurally.
    """

    page_count: int

    def page_text(self, page_number: int) -> str | None:
        """Extracted text for a page, or None if it was never captured."""
        ...


def verify_finding(finding: Finding, document: EvidenceSource) -> VerificationResult:
    """Verify one model-proposed finding against the document."""
    evidence = finding.evidence

    # --- 1. Evidence present -------------------------------------------
    if evidence is None:
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            reasons=[VerificationReason.MISSING_EVIDENCE],
        )

    if is_blank(evidence.quote):
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            reasons=[VerificationReason.EMPTY_QUOTE],
        )

    if len(evidence.quote) > MAX_QUOTE_CHARS:
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            reasons=[VerificationReason.QUOTE_TOO_LONG],
        )

    # --- 2. Page exists -------------------------------------------------
    if not _page_in_range(evidence.page, document.page_count):
        # A citation outside the document is a fabrication, not an uncertainty.
        return VerificationResult(
            status=VerificationStatus.REJECTED,
            reasons=[VerificationReason.INVALID_PAGE],
        )

    page_text = document.page_text(evidence.page)
    if page_text is None:
        # The page is real but its text was never captured (a scanned page, say).
        # We cannot judge the claim either way, and must not pretend otherwise.
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            page_match=True,
            reasons=[VerificationReason.PAGE_NOT_EXTRACTED],
        )

    # --- 3. Quote occurs on that page -----------------------------------
    match_type, matched_window = find_quote(evidence.quote, page_text)
    if match_type is QuoteMatchType.NONE:
        return VerificationResult(
            status=VerificationStatus.REJECTED,
            page_match=True,
            quote_match_type=QuoteMatchType.NONE,
            reasons=[VerificationReason.QUOTE_NOT_FOUND],
        )

    # --- 4. Values in the claim agree with the source --------------------
    # Checked against the quote and the page together: a claim may legitimately
    # reference a section number that sits just outside the quoted span.
    source_text = f"{matched_window}\n{page_text}"
    comparison = compare_numbers(finding.claim, source_text)

    reasons: list[VerificationReason] = []
    numeric_match = comparison.result is not Comparison.MISMATCH
    date_match = not comparison.mismatched_dates

    if comparison.unmatched:
        reasons.append(
            VerificationReason.CURRENCY_MISMATCH
            if comparison.has_currency_mismatch
            else VerificationReason.NUMERIC_MISMATCH
        )
    if comparison.mismatched_dates:
        reasons.append(VerificationReason.DATE_MISMATCH)
    if comparison.unresolved_dates:
        reasons.append(VerificationReason.DATE_AMBIGUOUS)

    if comparison.result is Comparison.MISMATCH:
        # The quote is real but the claim built on it misstates a value.
        status = VerificationStatus.REJECTED
    elif comparison.result is Comparison.UNKNOWN:
        status = VerificationStatus.PARTIALLY_VERIFIED
    else:
        status = VerificationStatus.VERIFIED

    return VerificationResult(
        status=status,
        page_match=True,
        quote_match=True,
        numeric_match=numeric_match,
        date_match=date_match,
        quote_match_type=match_type,
        reasons=reasons,
    )


def verify_analysis(analysis: ModelAnalysis, document: EvidenceSource) -> list[VerifiedFinding]:
    """Verify every finding in a model's proposal.

    Findings are judged independently: one fabricated citation does not
    discredit a correctly grounded one beside it.
    """
    results = [
        VerifiedFinding(finding=finding, verification=verify_finding(finding, document))
        for finding in analysis.findings
    ]

    # Metadata only - claims and quotes are document content and are not logged.
    counts: dict[str, int] = {}
    for item in results:
        key = str(item.verification.status)
        counts[key] = counts.get(key, 0) + 1
    logger.info("verification complete findings=%d outcomes=%s", len(results), counts)

    return results


def _page_in_range(page: int, page_count: int) -> bool:
    return 1 <= page <= page_count


def all_text(document: EvidenceSource) -> str:
    """Every extracted page, joined. For checks that span the whole document.

    Most verification is deliberately local - a claim is judged against the
    sentence its evidence sits in, not the file. A definition is the exception:
    a term defined twice and differently is a document-level fact, and the two
    definitions are rarely on the same page.
    """
    return "\n".join(
        text
        for page in range(1, document.page_count + 1)
        if (text := document.page_text(page)) is not None
    )


def find_quote(quote: str, page_text: str) -> tuple[QuoteMatchType, str]:
    """Locate `quote` within `page_text`, tolerating formatting only.

    Returns the match type and the region of the page it matched, which the
    caller uses as the primary source for value comparison.

    A near match must clear both bars: high textual similarity AND every value
    in the quote actually present in the matched region. Similarity alone is not
    enough - "30 days" and "60 days" are textually close and legally opposite.
    """
    normalized_quote = normalize(quote)
    normalized_page = normalize(page_text)

    if not normalized_quote or not normalized_page:
        return QuoteMatchType.NONE, ""

    index = normalized_page.find(normalized_quote)
    if index != -1:
        return QuoteMatchType.EXACT, normalized_page[index : index + len(normalized_quote)]

    window = _best_window(normalized_quote, normalized_page)
    if window is None:
        return QuoteMatchType.NONE, ""

    ratio = SequenceMatcher(None, window, normalized_quote, autojunk=False).ratio()
    if ratio < NEAR_MATCH_THRESHOLD:
        return QuoteMatchType.NONE, ""

    # Similarity got us here; meaning decides. Two guards, because textual
    # closeness and legal equivalence are different things.

    # Values: any figure in the quote absent from the matched region means this
    # is a different statement.
    if compare_numbers(normalized_quote, window).result is not Comparison.MATCH:
        return QuoteMatchType.NONE, ""

    # Polarity: inserting or dropping a single "not" is a tiny textual edit and
    # a total reversal of meaning. Similarity scoring cannot see the difference,
    # so it is checked explicitly.
    if _polarity_differs(normalized_quote, window):
        return QuoteMatchType.NONE, ""

    return QuoteMatchType.NEAR, window


#: Words that invert or restrict the meaning of a clause. A difference in these
#: between a quote and the text it supposedly came from is never cosmetic.
NEGATION_TERMS = frozenset(
    {"not", "no", "never", "cannot", "nor", "neither", "without", "unless", "except"}
)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _polarity_differs(quote: str, window: str) -> bool:
    """Whether quote and window disagree on meaning-inverting words.

    Counts, not just presence: "not ... not" differs from a single "not".
    Deliberately conservative - a mismatch here rejects the quote rather than
    risking a reversed clause being shown as verified.
    """
    return _negation_counts(quote) != _negation_counts(window)


def _negation_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in _WORD.finditer(text):
        word = match.group(0)
        if word in NEGATION_TERMS:
            counts[word] = counts.get(word, 0) + 1
    return counts


def _best_window(quote: str, page: str) -> str | None:
    """Find the region of `page` most likely to correspond to `quote`.

    Anchors on the longest shared run, then takes a quote-sized window around
    it. Bounded work: one SequenceMatcher pass, no sliding scan.
    """
    matcher = SequenceMatcher(None, page, quote, autojunk=False)
    block = matcher.find_longest_match(0, len(page), 0, len(quote))
    if block.size == 0:
        return None

    # Align the window so the shared run sits where it does inside the quote.
    start = max(0, block.a - block.b)
    end = min(len(page), start + len(quote))

    # Snap to word boundaries: a window cut mid-word would turn "not" into "ot"
    # and make the polarity check fire on an artefact of the slicing.
    while start > 0 and not page[start - 1].isspace():
        start -= 1
    while end < len(page) and not page[end].isspace():
        end += 1

    return page[start:end]
