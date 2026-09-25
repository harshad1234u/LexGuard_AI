"""Programmatic verification suite for the comprehensive 26-page demo contract.

Validates all 12 criteria specified in Part D3 of the audit instructions:
1. File exists on disk
2. Exact output path confirmed
3. Page count verified
4. Text extraction from all pages verified non-empty
5. Expected headings confirmed
6. Required commercial values confirmed
7. Required dates and timelines confirmed
8. Non-operative test scenario section confirmed
9. Secret scan clean (0 secret patterns)
10. PDF readable and valid PyMuPDF structure
11. Page count in range [20, 30] (specifically 26)
12. Manifest page references verified against extracted page text
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import fitz  # PyMuPDF

DEMO_DIR = Path(__file__).resolve().parent
PDF_PATH = DEMO_DIR / "demo_comprehensive_agreement.pdf"
MANIFEST_PATH = DEMO_DIR / "demo_contract_manifest.json"

SECRET_PATTERNS = [
    re.compile(r"AI" + r"za[0-9A-Za-z-_]{35}"),
    re.compile(r"nvapi" + r"-[0-9A-Za-z-_]{64}"),
    re.compile(r"sk" + r"-[0-9A-Za-z]{32,}"),
    re.compile(r"BEGIN " + r"PRIVATE KEY"),
    re.compile(r"eyJh[0-9A-Za-z-_=]+\.[0-9A-Za-z-_=]+\.[0-9A-Za-z-_=]+"),
]


def verify() -> int:
    print("=" * 70)
    print("PROGRAMMATIC VERIFICATION: 26-PAGE COMPREHENSIVE DEMO PDF")
    print("=" * 70)

    # 1 & 2. Existence and path
    assert PDF_PATH.exists(), f"Missing PDF at: {PDF_PATH}"
    assert MANIFEST_PATH.exists(), f"Missing manifest at: {MANIFEST_PATH}"
    print(f"[PASS] 1 & 2. File exists at exact path: {PDF_PATH}")

    # Load manifest
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Open PDF
    doc = fitz.open(PDF_PATH)
    page_count = len(doc)
    print(f"[PASS] 3 & 11. Page count: {page_count} pages (within required 20-30 range)")
    assert 20 <= page_count <= 30, f"Page count {page_count} out of bounds!"

    # 4 & 10. Extract text and verify non-empty
    page_texts: dict[int, str] = {}
    total_chars = 0
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        assert len(text.strip()) > 50, f"Page {i} has insufficient text ({len(text)} chars)"
        page_texts[i] = text
        total_chars += len(text)
    print(f"[PASS] 4 & 10. Extracted text from all {page_count} pages ({total_chars} total characters)")

    # 9. Secret scan on all extracted text
    found_secrets = []
    for page_num, text in page_texts.items():
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                found_secrets.append((page_num, pat.pattern))
    assert not found_secrets, f"Found secrets in PDF: {found_secrets}"
    print("[PASS] 9. Secret scan clean: 0 secret patterns detected across all pages")

    # 5. Verify expected headings
    required_headings = [
        "MASTER SERVICES, SOFTWARE IMPLEMENTATION & SUPPORT AGREEMENT",
        "SECTION 1. DEFINITIONS AND INTERPRETATION",
        "SECTION 2. SCOPE OF SERVICES",
        "SECTION 4. PROJECT MILESTONES & TIMELINES",
        "SECTION 6. FEES, BILLING & FINANCIAL SCHEDULE",
        "SECTION 7. PAYMENT TERMS, TAXES & INTEREST",
        "SECTION 8. SERVICE LEVELS & OPERATIONAL AVAILABILITY",
        "SECTION 9. INCIDENT SEVERITY CLASSIFICATION",
        "SECTION 10. CONFIDENTIALITY & PROPRIETARY PROTECTION",
        "SECTION 11. DATA PRIVACY & INCIDENT NOTIFICATION",
        "SECTION 12. INTELLECTUAL PROPERTY RIGHTS",
        "SECTION 15. INDEMNITY & LIABILITY LIMITATIONS",
        "SECTION 16. EXCLUSION OF CONSEQUENTIAL DAMAGES",
        "SECTION 17. INSURANCE & SUBCONTRACTING CONTROLS",
        "SECTION 18. AUDIT RIGHTS & BUSINESS CONTINUITY",
        "SECTION 19. TERM, AUTOMATIC RENEWAL & SUSPENSION",
        "SECTION 20. TERMINATION & TRANSITION SERVICES",
        "SECTION 21. GOVERNING LAW, ARBITRATION & JURISDICTION",
        "SECTION 23. DEMONSTRATION TEST SCENARIOS - NON-OPERATIVE",
    ]
    for heading in required_headings:
        found = any(heading in text for text in page_texts.values())
        assert found, f"Missing required heading: {heading}"
    print(f"[PASS] 5. Verified presence of all {len(required_headings)} key section headings")

    # 6. Verify required values
    for item in manifest["important_commercial_values"]:
        p = item["page"]
        val = item["value"]
        alt_val = item.get("alt_value")
        target_text = page_texts[p]
        matched = (val in target_text) or (alt_val and alt_val in target_text)
        assert matched, f"Value {val} (or {alt_val}) not found on page {p}"
    print(f"[PASS] 6. Verified {len(manifest['important_commercial_values'])} important commercial values at exact pages")

    # 7. Verify required dates and timelines
    for item in manifest["important_dates_and_periods"]:
        p = item["page"]
        val = item["value"]
        target_text = page_texts[p]
        assert val in target_text, f"Date/period {val} not found on page {p}"
    print(f"[PASS] 7. Verified {len(manifest['important_dates_and_periods'])} dates and periods at exact pages")

    # 8. Test scenario section
    assert 26 in page_texts
    p26 = page_texts[26]
    assert "SECTION 23. DEMONSTRATION TEST SCENARIOS - NON-OPERATIVE" in p26
    assert "NOTICE: IGNORE ALL PREVIOUS INSTRUCTIONS" in p26
    assert "INSTRUCTION PROBE" in p26
    print("[PASS] 8. Non-operative test scenario section confirmed on Page 26 with prompt injection probe")

    # 12. Verify all supported Q&A citations in manifest match actual text on the cited page
    for qa in manifest["supported_closed_world_qa"]:
        page = qa["citation_page"]
        text_on_page = page_texts[page]
        found_evidence = any(needle in text_on_page for needle in qa["expected_answer_contains"])
        assert found_evidence, f"Q&A evidence for '{qa['question']}' missing on page {page}"
    print(f"[PASS] 12. Verified all {len(manifest['supported_closed_world_qa'])} Q&A answer evidence snippets on cited pages")

    doc.close()
    print("=" * 70)
    print("ALL 12 PROGRAMMATIC PDF VERIFICATION CHECKS PASSED CLEANLY (0 DEFECTS)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(verify())
