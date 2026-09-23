"""The explicit, application-controlled view of a document sent to a model.

Only what is built here ever reaches a provider. Nothing is read from the
filesystem at send time and no application state is passed through, so a
provider cannot be handed secrets, unrelated files or internal objects by
accident (docs/04_SECURITY_GROUNDING.md sec. 2).

Page identity is preserved end to end. The model cites a page number, and the
verifier looks that page up in the same numbering - so a citation is traceable
rather than a guess about where in a wall of text something appeared.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

#: Delimiters that frame each page. Chosen to be visually distinct from clause
#: numbering so the model does not confuse them with document structure.
PAGE_OPEN = "<<<PAGE {number}>>>"
PAGE_CLOSE = "<<<END PAGE {number}>>>"

#: Any occurrence of the delimiter syntax inside document text is neutralised
#: before rendering. Otherwise a crafted PDF could close the untrusted-data
#: block early and have the rest of its text read as trusted instruction.
_DELIMITER_LIKE = re.compile(r"<<<\s*(/?END\s+)?PAGE[^>]*>>>", re.IGNORECASE)
_NEUTRALISED = "[page-marker removed]"


class DocumentPage(BaseModel):
    """One page of extracted text, as the application captured it."""

    page_number: int
    text: str


class DocumentPayload(BaseModel):
    """Everything a model is permitted to see about one document."""

    document_id: str
    total_pages: int = Field(description="Total pages in the document, counted by the application.")
    pages: list[DocumentPage] = Field(default_factory=list)

    @property
    def supplied_page_numbers(self) -> list[int]:
        return [page.page_number for page in self.pages]

    def render(self) -> str:
        """Render as delimited text with page boundaries intact."""
        blocks = []
        for page in sorted(self.pages, key=lambda p: p.page_number):
            body = _DELIMITER_LIKE.sub(_NEUTRALISED, page.text).strip()
            blocks.append(
                f"{PAGE_OPEN.format(number=page.page_number)}\n"
                f"{body}\n"
                f"{PAGE_CLOSE.format(number=page.page_number)}"
            )
        return "\n\n".join(blocks)


def build_payload(document, *, document_id: str | None = None) -> DocumentPayload:
    """Build a payload from anything exposing `page_count` and `page_text`.

    Only pages whose text the application actually holds are included. A page
    that failed extraction is omitted rather than sent as an empty string,
    which would invite the model to treat it as a genuinely blank page.

    Structurally compatible with `DocumentRecord` and with the verifier's
    `EvidenceSource`, so the same object feeds the model and the check on it.
    """
    pages = [
        DocumentPage(page_number=number, text=text)
        for number in range(1, document.page_count + 1)
        if (text := document.page_text(number)) is not None
    ]

    resolved_id = document_id or getattr(document, "document_id", "unknown")
    return DocumentPayload(
        document_id=resolved_id,
        total_pages=document.page_count,
        pages=pages,
    )
