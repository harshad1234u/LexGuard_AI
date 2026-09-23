"""A deterministic index of the values a document literally contains.

This module is deliberately OUTSIDE the model-analysis path. Nothing here
calls a provider, and nothing here produces a claim:

    page text (already extracted)
        -> existing deterministic extractors
        -> values bound to their page
        -> API

The distinction it exists to preserve, stated exactly:

    "30 days - page 2"                     is an observation
    "the contract requires 30 days notice" is an interpretation

The first is what this module produces. The second is a legal reading, and it
belongs to the verified-findings path, where a model proposes it and the
verifier checks it. Mixing the two would hand a user an interpretation wearing
the authority of an extraction, which is the failure mode the whole project is
built to avoid.

So a value here carries no meaning, no importance and no risk. It is a string
that occurs in the document, and the page it occurs on.

WHY THIS IS USEFUL ANYWAY
-------------------------
The verified-findings path depends on the model proposing a finding at all. A
live run against the Phase 16 demo contract proposed nine findings and released
two, while the same document demonstrably contains eleven amounts, dates and
periods. A reader who wants to know what the money and the deadlines are should
not depend on the model having chosen to mention them.

It also works when the provider does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.documents import ValueKind
from app.verification.numeric import NumericKind, extract_dates, extract_numbers

#: Which numeric kinds are worth showing. INTEGER and DECIMAL are deliberately
#: excluded: a bare "3" or "1.5" carries no unit, so it says nothing on its own
#: and would bury the values that do.
_NUMERIC_KINDS: dict[NumericKind, ValueKind] = {
    NumericKind.CURRENCY: ValueKind.CURRENCY,
    NumericKind.PERCENTAGE: ValueKind.PERCENTAGE,
    NumericKind.DURATION: ValueKind.DURATION,
}

#: Display order within a page. Fixed so the same document always indexes
#: identically - a view that reshuffles itself between requests is not an index.
_KIND_ORDER: dict[ValueKind, int] = {
    ValueKind.CURRENCY: 0,
    ValueKind.PERCENTAGE: 1,
    ValueKind.DURATION: 2,
    ValueKind.DATE: 3,
}


@dataclass(frozen=True)
class IndexedValue:
    """One value, as the document writes it, bound to the page it is on."""

    kind: ValueKind
    value: str
    page: int
    ambiguous: bool = False
    """Dates only. True when the written form has more than one reading - a
    DD/MM versus MM/DD date, typically. Such a date is reported as written and
    never silently assigned a calendar meaning."""


def _as_written(page_text: str, raw: str) -> str:
    """Recover the document's own spelling of a token.

    The extractors scan casefolded, whitespace-collapsed text, so a token comes
    back as "rs 50,000" even though the page says "Rs 50,000". Showing the
    normalised form would misquote the document, and a value index that
    misquotes is worse than none.

    The token is located in the original page text, tolerating the line breaks
    the PDF put inside it, and the page's own characters are returned. If it
    cannot be located the normalised form is returned unchanged - a wrong case
    is a blemish, inventing text would be a defect.
    """
    parts = [re.escape(part) for part in raw.split()]
    if not parts:
        return raw

    match = re.search(r"\s+".join(parts), page_text, re.IGNORECASE)
    if match is None:
        return raw

    # Collapse the line breaks the PDF introduced, keeping the page's casing.
    return " ".join(match.group(0).split())


def index_page(page_text: str | None, page_number: int) -> list[IndexedValue]:
    """Every supported value on one page, deduplicated within that page.

    Deduplication is per page and case-insensitive: a page that says "30 days"
    twice lists it once, because the second occurrence tells a reader nothing
    new about that page. It is NOT applied across pages - "30 days" on page 2
    and on page 5 are two facts about two places, and collapsing them would
    hide one of them.
    """
    if not page_text or not page_text.strip():
        return []

    found: list[IndexedValue] = []
    seen: set[tuple[ValueKind, str]] = set()

    def add(kind: ValueKind, raw: str, *, ambiguous: bool = False) -> None:
        value = _as_written(page_text, raw)
        key = (kind, value.casefold())
        if key in seen:
            return
        seen.add(key)
        found.append(
            IndexedValue(kind=kind, value=value, page=page_number, ambiguous=ambiguous)
        )

    for token in extract_numbers(page_text):
        kind = _NUMERIC_KINDS.get(token.kind)
        if kind is not None:
            add(kind, token.raw)

    for token in extract_dates(page_text):
        # `ambiguous` is the extractor's own verdict. This module does not
        # decide what an unclear date means, and does not resolve it.
        add(ValueKind.DATE, token.raw, ambiguous=token.ambiguous)

    found.sort(key=lambda item: (_KIND_ORDER[item.kind], item.value.casefold()))
    return found


def index_values(document) -> list[IndexedValue]:
    """Index every page the application actually captured.

    `document` is anything exposing `page_count` and `page_text(n)` - the same
    duck type the verifier's `EvidenceSource` uses, so a real document record
    and a test fixture index identically.

    A page whose text was never captured yields nothing. It is not guessed at,
    and its absence is what the coverage gate on the endpoint exists to report.
    """
    values: list[IndexedValue] = []
    for page_number in range(1, document.page_count + 1):
        values.extend(index_page(document.page_text(page_number), page_number))
    return values
