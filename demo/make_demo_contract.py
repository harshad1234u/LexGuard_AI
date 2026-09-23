"""Generate the controlled demo contract used to rehearse and present the system.

The repository refuses to carry PDFs (`.gitignore`: uploaded legal documents must
never be committed), so the *source of truth is this file* and the PDF is built
from it on demand - the same convention `frontend/e2e/make_fixtures.py` follows
for the browser fixtures.

    backend/.venv/Scripts/python.exe demo/make_demo_contract.py

Writes `demo/demo_services_agreement.pdf` (3 pages), which `.gitignore` excludes
via the global `*.pdf` rule. Nothing here needs a .gitignore change.

WHAT THIS DOCUMENT IS
---------------------
A fictional services agreement written for demonstration. It contains no real
party, no real person, no real address and no confidential information. It has
no legal effect and is not legal advice. Page 1 says so on the page itself, so
the statement travels with the file rather than only with this script.

WHY THE CLAUSES ARE SHAPED THIS WAY
-----------------------------------
Each clause is a self-contained paragraph carrying one checkable fact, so a
model-proposed finding can be bound to one piece of evidence:

    page 1   term and automatic renewal, with a 60-day notice condition
    page 2   a monthly fee, a payment window, an interest rate
    page 2   termination on 30 days notice, and termination for breach
    page 3   a confidentiality PROHIBITION, a liability cap, governing law

The renewal clause carries its condition deliberately: "renews automatically
*unless* notice is given" is the case where an answer that drops the condition
should be withheld.

TWO DELIBERATE DRAFTING CHOICES, BOTH MEASURED
----------------------------------------------
1. `Rs` rather than the rupee sign. PyMuPDF's base-14 Helvetica has no glyph
   for U+20B9, and a probe confirmed it extracts as a middle dot ("·50,000"),
   which would break value verification and misrepresent the document. `Rs` is
   in the verifier's currency vocabulary, renders, and round-trips.
2. ASCII only, asserted below. A typographic apostrophe or dash would survive
   rendering but invites encoding differences between the page and a quote.

Neither choice is a workaround for a defect; both keep the demo honest about
what the extractor actually captured.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

OUTPUT = Path(__file__).parent / "demo_services_agreement.pdf"

#: Rendering constants. Lines are pre-wrapped below rather than flowed, so the
#: extracted text is identical on every machine that runs this script.
MARGIN_X = 64
TOP_Y = 72
LINE_HEIGHT = 15
FONT = "helv"
BODY_SIZE = 10
TITLE_SIZE = 13

PAGES: tuple[tuple[str, ...], ...] = (
    # --- Page 1 ---------------------------------------------------------
    (
        "@title:DEMONSTRATION DOCUMENT - NOT A REAL AGREEMENT",
        "",
        "This fictional contract was created solely to demonstrate the PromptWars",
        "Legal AI system. The parties named below do not exist. It has no legal",
        "effect and it is not legal advice.",
        "",
        "@title:SERVICES AGREEMENT",
        "",
        "This Services Agreement is made between Northwind Analytics Private",
        "Limited, a company incorporated in India (the \"Client\"), and Meridian Data",
        "Services Private Limited, a company incorporated in India (the \"Service",
        "Provider\").",
        "",
        "1. SERVICES",
        "",
        "The Service Provider shall provide data preparation and reporting services",
        "to the Client as described in Schedule A.",
        "",
        "2. TERM AND RENEWAL",
        "",
        "This Agreement begins on 1 April 2026 and continues for an initial term of",
        "12 months. This Agreement shall renew automatically for successive periods",
        "of 12 months unless either party gives written notice of non-renewal at",
        "least 60 days before the end of the then-current term.",
    ),
    # --- Page 2 ---------------------------------------------------------
    (
        "3. FEES AND PAYMENT",
        "",
        "The Client shall pay the Service Provider a fee of Rs 50,000 per month for",
        "the Services. Each invoice shall be paid within 15 days of the invoice",
        "date. Overdue amounts shall bear interest at 1.5% per month.",
        "",
        "4. TERMINATION",
        "",
        "Either party may terminate this Agreement by giving 30 days written notice",
        "to the other party. Either party may terminate this Agreement immediately",
        "if the other party commits a material breach and fails to remedy that",
        "breach within 15 days of receiving written notice of the breach.",
        "",
        "5. EXPENSES",
        "",
        "The Client shall reimburse travel expenses that it has approved in advance",
        "in writing. The Client is not required to reimburse any other expense.",
    ),
    # --- Page 3 ---------------------------------------------------------
    (
        "6. CONFIDENTIALITY",
        "",
        "The Service Provider must not disclose Confidential Information to any",
        "third party without the prior written consent of the Client. This",
        "obligation continues for 3 years after this Agreement ends.",
        "",
        "7. LIMITATION OF LIABILITY",
        "",
        "The total liability of either party under this Agreement shall not exceed",
        "Rs 6,00,000 in aggregate.",
        "",
        "8. GOVERNING LAW AND JURISDICTION",
        "",
        "This Agreement is governed by the laws of India. The courts at Chennai",
        "shall have exclusive jurisdiction over any dispute arising out of this",
        "Agreement.",
        "",
        "9. NOTICES",
        "",
        "Any notice under this Agreement shall be in writing and sent to the",
        "registered address of the receiving party.",
        "",
        "Signed for and on behalf of the parties by their authorised signatories.",
        "",
        "[Client - Authorised Signatory]",
        "[Service Provider - Authorised Signatory]",
    ),
)


def build(path: Path) -> None:
    """Write the three-page PDF, one pre-wrapped line at a time."""
    document = fitz.open()
    try:
        for lines in PAGES:
            page = document.new_page()
            y = TOP_Y
            for line in lines:
                if line.startswith("@title:"):
                    page.insert_text(
                        (MARGIN_X, y), line.removeprefix("@title:"),
                        fontname=FONT, fontsize=TITLE_SIZE,
                    )
                elif line:
                    page.insert_text(
                        (MARGIN_X, y), line, fontname=FONT, fontsize=BODY_SIZE
                    )
                y += LINE_HEIGHT
        document.save(path)
    finally:
        document.close()


def main() -> None:
    for lines in PAGES:
        for line in lines:
            if not line.isascii():
                raise SystemExit(f"non-ASCII text would not round-trip: {line!r}")

    build(OUTPUT)
    print(f"wrote {OUTPUT} ({len(PAGES)} pages)")


if __name__ == "__main__":
    main()
