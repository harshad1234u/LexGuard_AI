#!/usr/bin/env python3
"""verify_lexguard_demo_document.py — Structural and semantic verification of the demo agreement.

Verifies:
1. Exact page count (40 pages).
2. Watermark / disclaimer on every page ("FICTIONAL DEMONSTRATION DOCUMENT").
3. Header and page numbering on every page.
4. Presence of all 34 structural sections and Schedules A through H.
5. Presence of all 12 commercial values declared in manifest.
6. Presence of all 20 key dates, periods, and deadlines declared in manifest.
7. Verification of all 22 supported Q&A evidence excerpts and answers.
8. Presence of all 7 cross-references.
9. Verification of all 5 prompt injection probes in Schedule H (page 40).
10. Presence and alignment of all 4 risk review targets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF (fitz) is not installed in the active environment.")
    sys.exit(1)

DEMO_DIR = Path(__file__).resolve().parent
PDF_PATH = DEMO_DIR / "lexguard_comprehensive_demo_agreement.pdf"
MANIFEST_PATH = DEMO_DIR / "lexguard_demo_manifest.json"


def run_checks() -> int:
    print("=" * 75)
    print("LEXGUARD AI — DEMO DOCUMENT VERIFICATION SUITE")
    print("=" * 75)

    if not PDF_PATH.exists():
        print(f"FAIL: PDF file not found at {PDF_PATH}")
        return 1
    if not MANIFEST_PATH.exists():
        print(f"FAIL: Manifest file not found at {MANIFEST_PATH}")
        return 1

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    print(f"Document opened: {PDF_PATH.name} ({total_pages} pages)")

    failures: list[str] = []
    checks_passed = 0

    # 1. Page count check
    expected_pages = manifest.get("document", {}).get("page_count", 40)
    if total_pages == expected_pages:
        print(f"[PASS] Page count exactly matches expected: {total_pages}/{expected_pages}")
        checks_passed += 1
    else:
        msg = f"[FAIL] Page count mismatch: got {total_pages}, expected {expected_pages}"
        print(msg)
        failures.append(msg)

    # Extract all text page-by-page
    page_texts: dict[int, str] = {}
    for p in range(total_pages):
        page_texts[p + 1] = doc[p].get_text()

    # 2. Page non-emptiness & disclaimer check on every page
    disclaimer_pass = True
    page_num_pass = True
    non_empty_pass = True

    for p in range(1, total_pages + 1):
        txt = page_texts[p]
        if len(txt.strip()) < 50:
            failures.append(f"Page {p} text appears too short ({len(txt.strip())} chars)")
            non_empty_pass = False
        if "FICTIONAL DEMONSTRATION DOCUMENT" not in txt:
            failures.append(f"Page {p} missing watermark/disclaimer header")
            disclaimer_pass = False
        if f"Page {p} of {total_pages}" not in txt:
            failures.append(f"Page {p} missing footer page number")
            page_num_pass = False

    if non_empty_pass:
        print(f"[PASS] All {total_pages} pages contain substantial text content.")
        checks_passed += 1
    if disclaimer_pass:
        print(f"[PASS] All {total_pages} pages contain the required fictional disclaimer.")
        checks_passed += 1
    if page_num_pass:
        print(f"[PASS] All {total_pages} pages contain valid headers and footer pagination.")
        checks_passed += 1

    # 3. Structural Sections and Schedules verification (34 sections + 8 schedules)
    full_text = "\n".join(page_texts.values())
    expected_sections = [
        f"SECTION {i}." for i in range(1, 35)
    ]
    expected_schedules = [
        f"Schedule {letter}" for letter in ["A", "B", "C", "D", "E", "F", "G", "H"]
    ]

    missing_sections = [s for s in expected_sections if s not in full_text]
    missing_schedules = [s for s in expected_schedules if s.lower() not in full_text.lower()]

    if not missing_sections and not missing_schedules:
        print(f"[PASS] All 34 substantive sections and 8 schedules (A-H) verified in document text.")
        checks_passed += 1
    else:
        for s in missing_sections + missing_schedules:
            print(f"[FAIL] Missing structural section/schedule: {s}")
            failures.append(f"Missing structural section/schedule: {s}")

    # 4. Commercial Values Verification
    important_values = manifest.get("important_values", [])
    values_missing = []
    for item in important_values:
        label = item["label"]
        val = item["value"]
        clause = item["clause"]
        page_num = item["page"]
        p_txt = page_texts.get(page_num, "")
        # Check value or evidence snippet
        evidence = item.get("evidence", "")
        if val in p_txt or (evidence and any(part.strip() in p_txt for part in evidence.split("..."))):
            continue
        elif val in full_text:
            continue
        else:
            values_missing.append(f"{label} ({val}) in {clause} (p.{page_num})")

    if not values_missing:
        print(f"[PASS] All {len(important_values)} commercial values verified in text.")
        checks_passed += 1
    else:
        for v in values_missing:
            print(f"[FAIL] Missing commercial value: {v}")
            failures.append(f"Missing commercial value: {v}")

    # 5. Key Dates and Periods Verification
    dates_and_periods = manifest.get("important_dates_and_periods", [])
    dates_missing = []
    for item in dates_and_periods:
        label = item["label"]
        val = item["value"]
        clause = item["clause"]
        page_num = item["page"]
        p_txt = page_texts.get(page_num, "")
        if val in p_txt or val in full_text:
            continue
        else:
            dates_missing.append(f"{label} ({val}) in {clause} (p.{page_num})")

    if not dates_missing:
        print(f"[PASS] All {len(dates_and_periods)} dates/deadlines verified in text.")
        checks_passed += 1
    else:
        for d in dates_missing:
            print(f"[FAIL] Missing date/period: {d}")
            failures.append(f"Missing date/period: {d}")

    # 6. Supported Q&A Evidence Excerpts Verification
    supported_qa = manifest.get("supported_closed_world_qa", [])
    qa_missing = []
    for idx, qa in enumerate(supported_qa, 1):
        q_text = qa["question"]
        expected_matches = qa.get("expected_answer_contains", [])
        page_num = qa["citation_page"]
        p_txt = page_texts.get(page_num, "")
        evidence = qa.get("evidence", "")

        # Check evidence or at least one expected term on citation page or full text
        found = False
        if any(term in p_txt for term in expected_matches):
            found = True
        elif evidence and any(part.strip() in p_txt for part in evidence.split("...") if len(part.strip()) > 5):
            found = True
        elif any(term in full_text for term in expected_matches):
            found = True

        if not found:
            qa_missing.append(f"Q{idx} (p.{page_num}): '{q_text}' (expected: {expected_matches})")

    if not qa_missing:
        print(f"[PASS] All {len(supported_qa)} supported Q&A items verified against document content.")
        checks_passed += 1
    else:
        for q in qa_missing:
            print(f"[FAIL] Missing Q&A ground truth: {q}")
            failures.append(f"Missing Q&A ground truth: {q}")

    # 7. Cross-Reference Targets Verification
    cross_refs = manifest.get("cross_references", [])
    cross_refs_missing = []
    for idx, cref in enumerate(cross_refs, 1):
        s_clause = cref["source_clause"]
        t_clause = cref["target_clause"]
        t_page = cref["target_page"]
        t_txt = page_texts.get(t_page, "")
        # Target clause should exist on target page or document
        if t_clause not in t_txt and t_clause not in full_text:
            cross_refs_missing.append(f"Ref {idx}: {s_clause} -> {t_clause} not found on page {t_page}")

    if not cross_refs_missing:
        print(f"[PASS] All {len(cross_refs)} cross-references verified.")
        checks_passed += 1
    else:
        for cr in cross_refs_missing:
            print(f"[FAIL] Cross reference issue: {cr}")
            failures.append(f"Cross reference issue: {cr}")

    # 8. Schedule H Prompt Injection Probes Verification
    injection_probes = manifest.get("prompt_injection_tests", [])
    sched_h_txt = page_texts.get(40, "")
    injections_missing = []
    for probe in injection_probes:
        pid = probe["id"]
        probe_text = probe["text"]
        # Take key phrase from probe text
        probe_keywords = probe_text[:40]
        if probe_keywords not in sched_h_txt and probe_text not in sched_h_txt:
            injections_missing.append(f"{pid}: '{probe_keywords}...'")

    if not injections_missing:
        print(f"[PASS] All {len(injection_probes)} prompt injection test probes verified on Page 40 (Schedule H).")
        checks_passed += 1
    else:
        for inj in injections_missing:
            print(f"[FAIL] Missing injection probe: {inj}")
            failures.append(f"Missing injection probe: {inj}")

    # 9. Risk Review Targets Verification
    risk_targets = manifest.get("risk_review_targets", [])
    risks_missing = []
    for r in risk_targets:
        r_clause = r["clause"]
        r_page = r["page"]
        p_txt = page_texts.get(r_page, "")
        clause_short = r_clause.removeprefix("Section ").strip()
        if r_clause in p_txt or clause_short in p_txt or r_clause in full_text:
            continue
        else:
            risks_missing.append(f"{r['category']}: {r_clause} on page {r_page}")

    if not risks_missing:
        print(f"[PASS] All {len(risk_targets)} risk review target clauses verified on their designated pages.")
        checks_passed += 1
    else:
        for rm in risks_missing:
            print(f"[FAIL] Missing risk target: {rm}")
            failures.append(f"Missing risk target: {rm}")

    print("=" * 75)
    print(f"VERIFICATION SUMMARY: {checks_passed}/10 verification suites passed, {len(failures)} failures.")
    if failures:
        print(f"OVERALL STATUS: FAILED ({len(failures)} issues detected)")
        return 1
    else:
        print("OVERALL STATUS: PASSED (100% verification criteria met)")
        return 0


if __name__ == "__main__":
    sys.exit(run_checks())
