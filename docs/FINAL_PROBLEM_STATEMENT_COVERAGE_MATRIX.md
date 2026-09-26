# Final Problem Statement Coverage Matrix — LexGuard AI

**Project:** LexGuard AI — Legal Document Intelligence  
**Branch:** `migration/gemini`  
**Audit Date:** 2026-09-24  
**Status:** Pre-Submission Repository Audit  
**Authoritative Reference:** [`docs/11_PROMPTWARS_ALIGNMENT.md`](file:///d:/code_placed/promprtwar/docs/11_PROMPTWARS_ALIGNMENT.md)

---

## 1. Problem Statement Overview

The PromptWars official problem statement establishes the following challenge:

> **AI for Legal Assistance & Access**  
> Build a GenAI-powered solution that makes legal information and basic legal assistance more accessible by helping users understand, compare, and navigate legal documents and information.

Key governing principles from the official challenge:
1. Solutions must **provide information and assistance rather than replace professional legal advice**.
2. Listed use cases are **potential directions, not exhaustive and not prescriptive**. Creative and distinct use cases are encouraged.

### LexGuard AI Core Architectural Thesis
> **The LLM interprets the document; the application independently verifies what the LLM says.**

The LLM output is an untrusted proposal. No claim, quote, page, date, amount, party role, modal verb, or evidence reference is presented as verified unless the deterministic application verification and release gates approve it.

---

## 2. Taxonomy of Status Labels

All status labels in this matrix are used strictly and grounded in code:

| Label | Definition | Verification Standard |
|---|---|---|
| **Implemented** | Built, wired to user-facing UI surface, covered by automated test suites. | Passes backend pytest, frontend Oxlint/build, and Playwright E2E. |
| **Partially Implemented** | A defined, verified subset is built; the unbuilt or deferred scope is explicitly recorded. | Implemented portion is tested; limitations are documented and disclosed. |
| **API-Only** | Computed and returned by backend API, but **not rendered by frontend UI**. | API schema validated; omitted from UI by deliberate design or backlog. |
| **Not Implemented / Excluded** | Deliberately out of scope or not implemented, with documented legal or safety rationale. | No code exists; explicitly rejected to prevent safety or legal liability hazards. |

---

## 3. Comprehensive Problem Statement Coverage Matrix

### Part A: The Seven Official PromptWars Directions

| # | Official Direction | Status | Implementation Details | Verified Test / Evidence Reference |
|---|---|---|---|---|
| **1** | **Simplifying complex legal documents** | **Partially Implemented** | Each finding delivers a concise, plain-language `claim`, deterministically verified against quoted document evidence across 8 semantic axes. A broader narrative `explanation` is provided, but is explicitly labelled in the UI as *"Interpretation — not verified against the document"* and flagged `explanation_verified: false` in the API. (Full semantic verification of whole paragraphs is unfeasible without high false-positive rates). | Backend: `tests/test_findings_release.py`, `tests/test_semantics.py`<br>Playwright: `test('7. an unverified explanation is labelled as interpretation')` |
| **2** | **Comparing contracts, agreements, or policies** | **Not Implemented** | Strictly single-document architecture. The coverage controller, extraction engine, verification boundary, and workspace state are scoped exclusively to one document at a time. No multi-document diffing or cross-contract comparison is implemented. | Architectural Decision Record: `docs/09_DECISIONS.md`<br>PRD Scope: `docs/01_PRD.md` |
| **3** | **Highlighting important clauses, obligations, risks, or inconsistencies** | **Partially Implemented** (UI) + **API-Only** (`attention`) | **In UI:** Clauses are categorized into 11 legal domains (*parties, term, termination, payment, fees, renewal, confidentiality, liability, indemnity, governing law, dispute resolution*). Findings are grouped by document topic in the Document Overview navigation panel. Contradictory definitions of the same term are detected and evidence defining contested terms is refused.<br>**API-Only:** The backend calculates an `attention` score (`info`, `review`, `high`) derived from concrete extracted terms; this is returned in API responses but **not** rendered as visual badges in the frontend UI. It is never presented as legal risk advice. | Backend: `tests/test_definitions_phase14.py`, `tests/test_categories.py`<br>Playwright: `test('22. the overview groups released findings')`, `test('29. the evidence inspector shows the backend verdict')` |
| **4** | **Answering questions based on provided legal documents** | **Implemented** | Closed-world document Q&A via `POST /api/v1/documents/{id}/ask`. Questions are answered strictly from uploaded document pages, governed by the exact same coverage gate, evidence locator, and semantic verifiers as analysis findings. When support is absent, model proposals are discarded and the application responds with deterministic fallback ("I couldn't find support in the document"). | Backend: `tests/test_qa_gate.py`, `tests/test_qa_adversarial.py`<br>Playwright: `test('16. questions stay available')`, `test('18. a question the document does not answer is not shown as a failure')` |
| **5** | **Helping users understand their options and potential next steps** | **Not Implemented / Explicitly Excluded** | Suggesting strategic options or legal courses of action borders on the unauthorized practice of law and cannot be verified against the closed world of the contract. The application provides legal information, never tactical legal advice or recommendations. | Legal Boundary Invariant: `docs/04_SECURITY_GROUNDING.md`<br>Alignment Record: `docs/11_PROMPTWARS_ALIGNMENT.md` §5 |
| **6** | **Generating summaries, checklists, or other actionable outputs** | **Not Implemented / Explicitly Excluded** | Holistic multi-clause summaries cannot be bound to a single evidence sentence, introducing severe hallucination vulnerability. Instead, the application offers the **Document Overview** (structured topic grouping of released findings) and **Deterministic Value Index** (structured listing of dates, numbers, periods). No prose summary, checklist, or downloadable memo is generated. | Verification Invariant: `docs/09_DECISIONS.md`<br>Corpus Evaluation: `docs/06_EVALUATION_PLAN.md` |
| **7** | **Helping users prepare information or questions for a legal professional** | **Not Implemented** | While the structured findings, page citations, and value index equip users with precise factual references for attorney consultations, there is no specialized "interview question generator" or "attorney brief builder" feature. | Roadmapped for future iterations; omitted from current release. |

---

### Part B: Beyond the PromptWars Prompt (System Innovations)

| # | System Capability | Status | Implementation Details | Verified Test / Evidence Reference |
|---|---|---|---|---|
| **8** | **Application-Measured Document Coverage Gate** | **Implemented** | The application independently inspects the PDF file structure, extracts page count, verifies text extractability, and blocks analysis if pages are missing, corrupt, encrypted, or empty. The LLM is never trusted to report whether it read the entire document. | Backend: `tests/test_coverage_gate.py`<br>Playwright: `test('2. an incomplete document blocks analysis and says why')` |
| **9** | **Deterministic Evidence Verification** | **Implemented** | Every model-proposed quote is located via substring and normalized fuzzy matching against PyMuPDF page text. If the quote does not appear on the designated page, or if figures or dates differ, the finding is withheld. | Backend: `tests/test_text_normalization.py`, `tests/test_grounding.py`<br>Playwright: `test('4. a withheld finding is never shown as verified')` |
| **10** | **Closed-Vocabulary Semantic Verifier (8 Axes)** | **Implemented** | Deterministic check across 8 semantic dimensions: (1) Polarity/negation inversion, (2) Modality shift (may vs shall), (3) Party role binding (buyer vs seller in active/passive voice), (4) Conditionality dropping (if/unless/subject to), (5) Numeric exactness, (6) Temporal direction (before vs after), (7) Scope alteration, (8) Definition conflict. | Backend: `tests/test_semantics.py`, `tests/test_polarity.py`, `tests/test_modality.py`<br>Adversarial Suite: `eval_harness.py` (39/39 attacks caught, 0% FN) |
| **11** | **Prompt Injection Defense in Document Text** | **Implemented** | Untrusted document text containing imperative instructions directed at the assistant (e.g. "Ignore previous instructions", "State that provider has no obligations") is detected and disqualified from serving as valid contractual evidence. | Backend: `tests/test_injection_defense.py`<br>Evaluation: `eval_independent.py` (7/7 injection attacks detected) |
| **12** | **Deterministic Value Index** | **Implemented** | Purely deterministic regex extraction of currencies, amounts, percentages, time periods, and calendar dates directly from document pages. Requires zero LLM calls; functions even during complete provider outage. | Backend: `tests/test_value_index.py`<br>Playwright: `test('8. extracted values are shown with page references')`, `test('10. values remain available when the model provider has failed')` |
| **13** | **Single Release Boundary** | **Implemented** | Architecture enforces a single chokepoint (`release_policy.py`) through which all findings and Q&A responses must pass. Unverified claims are stripped, dropped, or sanitized before reaching the API response layer. | Backend: `tests/test_findings_release.py`<br>Playwright: `test('25. the overview never publishes what the findings list does not')` |
| **14** | **Tamil Multi-Language Reading Support** | **Partially Implemented** | Provides a secondary Tamil translation alongside validated English findings and answers. Released only when English passes all verification gates and Tamil numeral/date representations match document evidence. Semantic checks in Tamil remain deferred; other languages excluded. | Backend: `tests/test_multilingual.py`<br>Playwright: `test('39. a Tamil analysis sends the language and labels the translation')`, `test('41. a Tamil question gets a labelled translation')` |
| **15** | **Cross-Finding Reasoning Notes (Nemotron)** | **Implemented** (Unverified by Design) | NVIDIA Nemotron 70B synthesizes thematic connections across released findings. Rendered in a dedicated card, visually segregated from findings, explicitly labelled as unverified reading assistance, and linked via keyboard shortcuts. | Backend: `tests/test_reasoning_notes.py`<br>Playwright: `test('36. a reasoning note is labelled, carries no verified badge, and is not a finding')` |
| **16** | **Full Provider Provenance Metadata** | **Implemented** | Every API response and UI view reports the exact analysis provider (`gemini`), reasoning provider (`nemotron`), model identifiers, and release policy version. | Backend: `tests/test_provenance.py`<br>Playwright: `test('35. provenance says who analysed, who reasoned, and who verified')` |
| **17** | **Document Overview Landmark Navigation** | **Implemented** | Landmark navigation panel grouping released findings under standard document topics. Operates as a strict projection: only findings that have cleared the release gate appear in the overview. | Backend: `tests/test_overview.py`<br>Playwright: `test('22. the overview groups released findings')`, `test('31. the workspace tabs are keyboard operable')` |
| **18** | **Single & Typographic Definition Conflict Detection** | **Implemented** | Pre-submission audit enhancement: `_DEFINITION` regex and `defines_a_contested_term` normalize and capture single quotes (`'...'`), single typographic quotes (`‘...’`), and double typographic quotes (`“...”`), preventing silent misses of conflicting definitions in UK/Commonwealth contracts. | Backend: `tests/test_definitions_phase14.py` (30/30 tests pass, including `TestSingleQuotesAreStillQuotes`) |

---

## 4. Alignment Conclusion

LexGuard AI directly addresses the core spirit of the PromptWars challenge—**making legal documents understandable and accessible**—while taking an uncompromising stance on **hallucination prevention and legal safety**. 

Rather than implementing wide, ungrounded conversational features (like autonomous chat or legal advice generation), LexGuard AI delivers a depth-first, evidence-grounded system where every user-facing claim is tied to real contractual text.
