"""Deterministic document-language detection (Phase 23).

The document's language is measured, not asked for: the model's opinion of it
is never used. The measure is deliberately simple - the share of letters in
the Tamil Unicode block - because what it feeds is labelling and audit, not
verification. Nothing is released or withheld on the strength of it.
"""

from __future__ import annotations

from typing import Iterable

#: Tamil Unicode block.
_TAMIL = range(0x0B80, 0x0C00)

#: Share of letters at or above which a text counts as that script.
DOMINANT = 0.8
#: Share of letters below which a script is treated as absent.
TRACE = 0.05


def detect_language(texts: Iterable[str]) -> str:
    """'en', 'ta', 'mixed' or 'other' for the given page texts.

    'en' here means "Latin script": the detector does not tell English from
    other Latin-script languages, and the docs say so.
    """
    tamil = latin = other = 0
    for text in texts:
        for char in text or "":
            if not char.isalpha():
                continue
            code = ord(char)
            if code in _TAMIL:
                tamil += 1
            elif char.isascii() or 0x00C0 <= code <= 0x024F:
                latin += 1
            else:
                other += 1

    letters = tamil + latin + other
    if letters == 0:
        return "other"
    tamil_share, latin_share = tamil / letters, latin / letters
    if tamil_share >= DOMINANT:
        return "ta"
    if latin_share >= DOMINANT:
        return "en"
    if tamil_share >= TRACE and latin_share >= TRACE:
        return "mixed"
    return "other"
