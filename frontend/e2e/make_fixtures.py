"""Generate the PDFs the browser tests upload.

The repository refuses to carry PDFs (`.gitignore`: uploaded legal documents
must never be committed), and these files are uninteresting anyway - three
pages of one sentence. Generating them keeps the rule intact and keeps the
browser run reproducible.

    backend/.venv/Scripts/python.exe frontend/e2e/make_fixtures.py

The *name* is the whole payload: `stub_backend.py` selects which safety state
to serve from the filename, so `withheld.pdf` and `verified.pdf` contain
identical text and produce entirely different screens.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

#: One per scenario in `stub_backend.py`, plus a non-PDF for the reject path.
SCENARIOS = (
    "verified",
    "withheld",
    "incomplete",
    "provider-failure",
    "qa-failure",
    "qa-recovers",
    "notfound",
    "interpretation",
    "novalues",
    "notext",
    "recovers",
)

SENTENCE = "Either party may terminate this agreement by providing 30 days written notice."


def build(path: Path, text: str, pages: int = 3) -> None:
    document = fitz.open()
    try:
        for index in range(pages):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {index + 1}. {text}")
        document.save(path)
    finally:
        document.close()


def main() -> None:
    directory = Path(__file__).parent / "fixtures"
    directory.mkdir(exist_ok=True)

    for scenario in SCENARIOS:
        build(directory / f"{scenario}.pdf", SENTENCE)

    (directory / "notes.txt").write_text(
        "This is not a PDF. Uploading it must be refused.\n", encoding="utf-8"
    )
    print(f"wrote {len(SCENARIOS) + 1} fixtures to {directory}")


if __name__ == "__main__":
    main()
