# Final Test Execution Report — LexGuard AI

**Project:** LexGuard AI — Legal Document Intelligence  
**Branch:** `migration/gemini`  
**Execution Timestamp:** 2026-09-24 22:38 IST  
**Environment:** Windows Server / Python 3.11.9 / Node.js v24.20.0 / Chromium (Playwright 1.63.0)  
**Overall Status:** **ALL REGRESSION, UNIT, INTEGRATION, BUNDLE, AND E2E SUITES PASSED (0 FAILURES)**

---

## 1. Executive Summary of Test Suites

| Test Suite | Framework / Tool | Scope | Total Tests | Passed | Failed | Skipped / Deselected | Duration |
|---|---|---|---|---|---|---|---|
| **Backend Unit & Verification** | `pytest` (8.3.4) | Coverage gates, deterministic grounding, semantics, Q&A, findings, release policy, definitions | 1,760 | **1,753** | 0 | 1 skipped, 6 deselected* | 57.36s |
| **Frontend Static Analysis** | `oxlint` | React/TypeScript code quality, safety patterns, syntax hygiene | 50 files | **50 files clean** | 0 | 0 warnings | 19ms |
| **Frontend Typecheck & Build** | `tsc -b && vite build` | Strict TypeScript types, client bundle compilation, tree-shaking | 58 modules | **Clean build** | 0 | 0 errors | 164ms |
| **Client Bundle Secret Audit** | `node check-bundle.mjs` | Regex scan of production distribution (`dist/`) for leaked credentials | `dist/` | **0 secrets** | 0 | None | <1s |
| **Frontend End-to-End E2E** | `@playwright/test` | Safety flows, multi-viewport UI (390px, 768px, 1280px, 1440px), provenance, Q&A | 46 | **46** | 0 | 0 | 55.6s |
| **Synthetic Eval Harness** | `eval_harness.py` | Grounding boundaries across 8 semantic attack vectors (hand-written cases) | 67 | **67** (100%) | 0 | 0 false negatives | 0.8s |
| **Independent Eval Corpus** | `eval_independent.py` | 4 contract families (construction, education, healthcare, insurance) | 75 | **69 scored** | 0 | 3 documented FN, 3 ambiguous | 1.1s |
| **Demo Contract Generator** | `make_demo_contract.py` | 3-page synthetic legal services agreement PDF generation | 1 script | **Generated** | 0 | None | <1s |

*\*Note: 1 test skipped (`test_live_gemini`) and 6 deselected because live integration tests require explicit `--run-live` flags and unthrottled provider quota.*

---

## 2. Detailed Suite Results

### 2.1 Backend Pytest Suite
- **Command:** `backend/.venv/Scripts/python.exe -m pytest --tb=short`
- **Result:** `1753 passed, 1 skipped, 6 deselected, 6 warnings in 57.36s`
- **Coverage Breakdown:**
  - `tests/test_coverage_gate.py`: PDF integrity, missing pages, encryption, zero-text detection.
  - `tests/test_text_normalization.py`: Ligatures, typographic quotes, zero-width spaces, soft hyphens.
  - `tests/test_grounding.py`: Quote substring extraction, exact fuzzy matching, page boundary assertions.
  - `tests/test_semantics.py`: Polarity negation, modal shift, active/passive actor binding, conditional dropping.
  - `tests/test_definitions_phase14.py`:
    - Contradictory definition detection across pages.
    - Typographic double-quote variants (`“...”, „...”`).
    - **Pre-submission audit fix (`TestSingleQuotesAreStillQuotes`):** Single straight quotes (`'...'`), single typographic quotes (`‘...’`), and internal apostrophes (`"Buyer's Representative"`) verified across 6 new tests (30/30 passed).
  - `tests/test_qa_gate.py` & `tests/test_qa_adversarial.py`: Q&A grounding, refusal on ungrounded questions, multi-sentence claim splitting.
  - `tests/test_findings_release.py`: Single release boundary, sanitization of unverified claims, provenance attachment.
  - `tests/test_multilingual.py`: Tamil translation gating, numeral and date consistency check.
  - `tests/test_reasoning_notes.py`: Nemotron reasoning note scoping, linking to source findings, non-verified labelling.

### 2.2 Frontend Linter & Typecheck
- **Command:** `npm run lint` (`oxlint`)
  - `Found 0 warnings and 0 errors. Finished in 19ms on 50 files with 116 rules.`
- **Command:** `npm run build` (`tsc -b && vite build`)
  - `✓ 58 modules transformed.`
  - `dist/index.html: 0.64 kB`
  - `dist/assets/index-*.css: 34.93 kB (gzip: 7.35 kB)`
  - `dist/assets/index-*.js: 307.10 kB (gzip: 90.03 kB)`
  - `✓ built in 164ms`

### 2.3 Frontend Secret Exposure Audit
- **Command:** `npm run check:bundle` (`node scripts/check-bundle.mjs`)
  - Scanned all production output files in `frontend/dist/`.
  - Searched for patterns: `AIza[0-9A-Za-z-_]{35}`, `nvapi-[A-Za-z0-9-_]{64}`, `eyJh...`, `BEGIN PRIVATE KEY`.
  - Output: `bundle check: no secret patterns in dist/`

### 2.4 Playwright Browser Test Suite
- **Command:** `npx playwright test`
- **Result:** `46 passed (55.6s)` across single-worker Chromium instance.
- **Key Validated Scenarios:**
  - **Test #1–#2:** Invalid file formats and incomplete/encrypted PDFs are refused; no analysis starts.
  - **Test #3–#4:** Verified findings display evidence and legal disclaimer; withheld findings are never displayed as verified.
  - **Test #7:** Unverified narrative explanations are prominently labelled as *"Interpretation — not verified against the document"*.
  - **Test #8–#11:** Value Index extracts numbers/dates with page citations; remains available during provider failure.
  - **Test #13–#15:** Provider failure displays a safe error message without blaming the document; manual retry works cleanly.
  - **Test #18–#21:** Unsupported questions fall back to safe application voice; question failure does not taint analysis findings.
  - **Test #22–#27:** Document Overview groups findings by topic; empty topics report analysis status; overview never leaks unreleased findings.
  - **Test #31–#34:** Tabs and inspector are fully keyboard-navigable; mobile viewports (390px) display inspector in an accessible bottom sheet.
  - **Test #35–#38:** Provenance displays exact providers; reasoning notes are labelled unverified and link to findings via keyboard.
  - **Test #39–#41:** Tamil reading mode sends requested language and labels translation; English sends no translation.
  - **Test #42:** Missing analysis key causes a clear stop, preventing silent fallback.
  - **Test #43 (390px, 768px, 1280px, 1440px):** Reasoning notes and findings layout fit cleanly with zero horizontal scrolling.

### 2.5 Synthetic Evaluation Harness (`eval_harness.py`)
- **Evaluation Purpose:** Measures the application's deterministic grounding boundary against hand-crafted adversarial attacks (no LLM calls; pure deterministic verifier).
- **Adversarial Attacks:**
  - Actor swaps (employer/employee, supplier/customer, lender/borrower): 6/6 caught
  - Conditionality dropped (if, unless, subject to, only if, provided that): 5/5 caught
  - Cross-references invented: 3/3 caught
  - Modality changes (may to shall, must to may, permitted to required): 6/6 caught
  - Multi-sentence contradictions: 3/3 caught
  - Polarity reversals (shall not to shall, no refund, not liable): 6/6 caught
  - Scope modifications (days changed, currency altered, some to all): 6/6 caught
  - Temporal shifts (date changed, fixed to permanent, before to after): 5/5 caught
- **Harness Metrics:**
  - Total Adversarial Cases: 39 | Detected: 39 | False Negatives: **0 (0.0%)**
  - Total Legitimate Cases: 28 | Correctly Released: 28 | False Positives: **0 (0.0%)**

### 2.6 Independent Legal Corpus Evaluation (`eval_independent.py`)
- **Corpus Design:** 75 realistic contract provisions authored across 4 distinct legal domains (Construction, Education, Healthcare, Insurance).
- **Detection Results:**
  - Construction: 14/15 attacks caught, 5/5 legitimate released
  - Education: 9/9 attacks caught, 4/4 legitimate released
  - Healthcare: 14/15 attacks caught, 6/6 legitimate released
  - Insurance: 12/13 attacks caught, 5/5 legitimate released
- **Overall Corpus Metrics:**
  - Total Adversarial Cases: 52
  - Attacks Detected: 49 (**94.2% Detection Rate**)
  - False Negatives: **3** (documented in §3)
  - Legitimate Cases: 20 (**100% Released, 0.0% False Positive Rate**)
  - Ambiguous Cases: 3 (recorded, excluded from scoring)

---

## 3. Disclosed Corpus False Negatives (Documented Limitations)

The 3 false negatives in `eval_independent.py` represent known, documented edge cases in contract drafting:

1. `hc_condition_dispute_carveout_dropped` (Healthcare):
   - *Clause:* "Invoices disputed in good faith may be withheld in part until the dispute is resolved."
   - *Attack Claim:* "Invoices may be withheld in part until the dispute is resolved."
   - *Analysis:* "disputed in good faith" is a restrictive condition clause lacking a standard conditional trigger word (*if/unless*). Caught in Phase 14 registry as an open research challenge.
2. `in_scope_exclusion_omitted` (Insurance):
   - *Clause:* "This Policy does not cover loss or damage arising from war, nuclear risk, or wilful misconduct of the Insured."
   - *Attack Claim:* "This Policy does not cover loss or damage arising from war or nuclear risk."
   - *Analysis:* The claim is a true subset of the exclusion list, but omitting "wilful misconduct" alters legal scope.
3. `ms_two_sentence_answer_one_false` (Construction):
   - *Clause:* "The Contractor shall maintain public liability insurance of not less than £5,000,000.00."
   - *Attack Claim:* Two sentences where the first is verbatim and the second invents professional indemnity insurance reusing the same £5,000,000 figure found on the page.

---

## 4. Test Execution Sign-Off

The test suite demonstrates comprehensive coverage across every tier of the LexGuard AI application:
- **Unit & Property Verification:** 1,753 tests passing.
- **Security & Secret Hygiene:** 0 secrets detected.
- **Frontend & End-to-End User Experience:** 46 Playwright tests passing across 4 viewports.
- **Adversarial Robustness:** 100% attack detection on synthetic harness; 94.2% on independent corpus.
