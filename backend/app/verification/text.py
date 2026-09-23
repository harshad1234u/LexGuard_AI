"""Text normalisation shared by the grounding and numeric verifiers.

Extracted PDF text and model-supplied quotes differ in ways that carry no
meaning: soft line breaks, ligatures, curly quotes, doubled spaces, words
hyphenated across a line. Normalisation removes exactly those differences so a
correct quote is not rejected over typography.

The hard rule, and the reason this lives in one place: normalisation must never
touch anything that could change a value. Digits, decimal points, thousands
separators, currency symbols and percent signs are left exactly as they are. A
normaliser that stripped commas would make "5,00,000" and "50,000" identical,
which is precisely the error this layer exists to catch.

This module is a separate file so `grounding` and `numeric` can both use it
without importing each other.
"""

from __future__ import annotations

import re
import unicodedata

# Ligatures PyMuPDF emits verbatim from embedded fonts.
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

# Typographic variants that mean the same character.
_PUNCTUATION = {
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "‚": "'",
    "‛": "'",
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "„": '"',
    "′": "'",  # prime
    "″": '"',  # double prime
    "–": "-",  # en dash
    "—": "-",  # em dash
    "―": "-",  # horizontal bar
    "−": "-",  # minus sign
    "…": "...",  # ellipsis
}

# Characters that carry no content and should simply disappear.
_ZERO_WIDTH = dict.fromkeys(
    ["​", "‌", "‍", "﻿", "­"],  # incl. soft hyphen
    "",
)

_TRANSLATIONS = str.maketrans({**_LIGATURES, **_PUNCTUATION, **_ZERO_WIDTH})

# A word split across a line break: "termina-\ntion" -> "termination".
# Restricted to letters on both sides so a range like "30-\n60" is never joined.
_HYPHEN_LINEBREAK = re.compile(r"(?<=[^\W\d_])-[ \t]*[\r\n]+[ \t]*(?=[^\W\d_])", re.UNICODE)

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str, *, casefold: bool = True) -> str:
    """Normalise text for comparison, preserving every value-bearing character.

    `casefold=False` is used where the caller needs offsets to stay meaningful
    against differently-cased source text.
    """
    if not text:
        return ""

    # NFC, not NFKC: NFKC would rewrite superscripts and fractions (turning
    # "5<sup>2</sup>" into "52"), which is a change of value, not of form.
    result = unicodedata.normalize("NFC", text)
    result = result.translate(_TRANSLATIONS)
    result = _HYPHEN_LINEBREAK.sub("", result)
    result = _WHITESPACE.sub(" ", result)
    result = result.strip()

    return result.casefold() if casefold else result


def collapse_for_numbers(text: str) -> str:
    """Normalisation for numeric scanning: form and spacing only, never digits."""
    return normalize(text, casefold=True)


def is_blank(text: str | None) -> bool:
    return not text or not text.strip()
