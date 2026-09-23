# PromptWars Legal AI — Product Requirements Document (PRD)

**Status:** current as of Phase 15 — MVP demo-ready with documented limitations
**Hackathon:** PromptWars — *AI for Legal Assistance & Access*
**Primary model:** NVIDIA Nemotron 3 Nano Omni 30B-A3B Reasoning (hosted NVIDIA API)
**Orchestration:** LangChain + LangGraph state machine
**Backend:** FastAPI + Python
**Frontend:** React + Vite + TypeScript + Tailwind CSS

> This document describes what the application **is**, not what was once
> planned. Anything not built is labelled as such. Alignment with the official
> problem statement is stated in `docs/11_PROMPTWARS_ALIGNMENT.md`.

---

## 1. Product positioning

> An evidence-grounded GenAI legal document intelligence system that helps
> users understand complex legal documents, identify important clauses and
> obligations, and ask questions based on uploaded documents, while
> independently verifying AI-generated findings against document evidence
> before release.

The core principle:

> **The LLM interprets the document; the application independently verifies
> what the LLM says.**

This is an informational assistance system. It provides **legal information**
and **document understanding**, not legal advice, and it is not a substitute
for a qualified lawyer.

## 2. Problem

Legal documents are hard for non-specialists to read, because of:

- complex language and long sentences,
- clauses that run across pages,
- obligations stated indirectly,
- restrictions and prohibitions phrased without the word "not",
- conditions and carve-outs attached to an otherwise simple right,
- dates, notice periods and renewal windows,
- monetary values, caps and percentages,
- defined terms and cross-references to other parts of the document,
- legal terminology with no everyday equivalent.

A conventional LLM chatbot can summarise or answer questions about such a
document while:

- overlooking portions of a long document,
- misreading a date, an amount or a notice period,
- producing claims the document does not support,
- confusing general legal knowledge with the uploaded document,
- reversing the effect of a clause (`must not` read as `may`),
- or offering no evidence a reader could check.

The product therefore prioritises **document grounding, traceability,
completeness measurement, and conservative output behaviour** over breadth of
features.

## 3. Target users

Realistic users of this tool, without invented research or statistics:

- students reading a course, hostel or internship agreement,
- freelancers reading a client contract or statement of work,
- employees reading an offer letter, employment contract or NDA,
- tenants reading a lease,
- small-business users reading a supplier, SaaS or service agreement,
- ordinary people reviewing an agreement before signing it,
- anyone preparing questions before speaking to a lawyer.

No user research was conducted. These are the readers the system was designed
for, stated as design intent rather than as findings.

## 4. Core MVP — what is actually implemented

Every capability in this section exists in the repository and is covered by
tests. Capabilities not listed here do not exist.

### 4.1 Document intake

| Capability | Detail |
|---|---|
| PDF upload | `POST /api/v1/documents/upload`, multipart. **PDF only** — DOCX is rejected at validation because its extraction path does not exist. |
| Document validation | Filename safety → size → extension → MIME type → file signature → parseability, in that order. Limits: 25 MB, 300 pages (configurable). |
| Repair detection | A PDF that PyMuPDF had to structurally rebuild is flagged `source_repaired` and is never eligible for a complete-document analysis, because its page count is itself reconstructed. |

### 4.2 Extraction and coverage

| Capability | Detail |
|---|---|
| Page-level text extraction | `POST /documents/{id}/extract`. Deterministic, entirely local, no model involved. |
| Per-page manifest | Every page recorded as `processed`, `empty`, `unreadable` or `failed`, with text length and image count. |
| Document coverage / integrity check | `coverage_status` computed by the application from its own counters: `pending`, `processing`, `complete`, `incomplete`, `failed`, `blocked_repaired`. |
| Coverage gate | `complete` is the only verdict permitting a complete-document analysis, and the model is not called otherwise. The model is never asked, and never told, whether the document was fully read. |

### 4.3 Analysis and findings

| Capability | Detail |
|---|---|
| Clause / finding extraction | `POST /documents/{id}/analyze` (asynchronous, 202 + `analysis_id`), polled at `GET /analysis/{id}/status`, results at `GET /documents/{id}/findings`. |
| Clause categories | Model-proposed and bounded: parties, term, termination, payment, fees, renewal, confidentiality, liability, indemnity, governing law, dispute resolution. Free-form by design, length-bounded, and refused if the text reads as an instruction. |
| Evidence quotes | Every finding carries a quote the verifier locates in the document. |
| Page references | Every finding carries the page the quote was found on. |
| Section citations | Model-supplied, then confirmed by whole-label containment against the cited page — or dropped. A fabricated citation is never shown. |
| Plain-language claim | One verified sentence per finding stating what the document provides. |
| Explanation | Two or three sentences for a non-lawyer. **Released but not verified**; see §6. |
| Attention level | **API-only.** `info` / `review` / `high`, **derived by the application** from the verified evidence. Not the model's choice, and not a legal risk assessment. Returned in the API response; the current frontend does **not** render this field, and visual attention badges are not implemented — see §4.8 and §6. |
| Withheld counts | Findings that did not survive verification are counted, never shown — not softened, not hedged, not given a confidence score. |

### 4.3a Deterministic value index

| Capability | Detail |
|---|---|
| Value index | `GET /documents/{id}/values`. Amounts, percentages, time periods and dates located in the extracted text, each bound to its page. |
| No model involvement | Built from the page text by the same deterministic extractors the verifier uses. Works while the provider is unavailable. |
| No interpretation | A value is a string that occurs in the document. It is **not** labelled a deadline, obligation, requirement or risk — establishing that is interpretation and belongs to §4.3. |
| Ambiguous dates | Reported as written and flagged; never resolved to a calendar date. |
| No prose | Only the value, its kind and its page are returned. No surrounding sentence. |
| Coverage-gated | 409 until every page has been read, so a partial document cannot under-report silently. |

The distinction this feature preserves:

```text
"30 days - page 2"                      an observation
"the contract requires 30 days notice"  an interpretation
```

### 4.4 Verification

| Capability | Detail |
|---|---|
| Deterministic evidence verification | Evidence present → page exists → quote occurs there → values agree. Each step can only lower a verdict. |
| Numeric and date validation | Currency, percentages, durations, quantities and dates, including continental (`€1.400.000,00`), Indian (`₹10,00,000`) and parenthesised-numeral (`forty-five (45) days`) formats. |
| Polarity guard | A difference in meaning-inverting words rejects a textually similar match. |
| Claim / evidence binding | A figure from one clause cannot support a claim about another; values are bound to the evidence sentence cited for that claim. |
| Semantic verification | Eight axes over closed vocabularies: polarity, modality, actor (including named-party role binding), conditions, certainty, scope, temporal direction, time limits. |
| Injection-aware evidence refusal | Text addressed to the assistant is refused as evidence even though it genuinely occurs in the file. |
| Reported speech and definition conflicts | Correspondence quoted as though it were a term is refused; a term defined twice and differently causes the evidence to be refused. |
| Verification statuses | `verified`, `partially_verified`, `unverified`, `rejected`. Only `verified` may be shown as an established fact. |

### 4.5 Document-grounded Q&A

| Capability | Detail |
|---|---|
| One question, one document | `POST /documents/{id}/ask`, synchronous, no chat history, no persona, no memory between questions. |
| Same gates as analysis | Coverage gate, evidence verifier and claim-level semantic checks, sharing one implementation with the findings path. |
| Support levels | `supported`, `partially_supported`, `not_found`. These are support levels, **not** confidence scores. |
| Safe fallback | The model's answer text is released only when at least one of its quotes verified. Otherwise the model's words are discarded and the application answers in its own voice: *"I couldn't find this information in the uploaded document."* — reporting that nothing could be confirmed, never that the clause does not exist. |

### 4.6 Output safety policy

A single release boundary (`app/verification/policy.py`) decides what a user
sees. Everything the findings endpoint publishes comes from it, the Q&A path
shares its citation check, and a run that never reached the boundary publishes
nothing rather than falling back on the model's proposal.

### 4.7 Model-output hardening

Malformed, truncated, prose-wrapped, fenced, oversized and adversarial model
output — including self-declared fields such as `verified`, `confidence`,
`risk_level` and `evidence_valid` — is dropped at parse and unreadable
thereafter. A validation error carries field names, never document text.

### 4.8 Frontend presentation

React + Vite + TypeScript + Tailwind. Screens: upload, document summary,
coverage panel, analysis progress, overview panel, findings panel, values
panel, ask panel, disclaimer.

- Verified findings render with the quote, page and confirmed citation inside
  the finding's own card; the evidence block is never collapsed.
- An unverified explanation is set apart and labelled *"Interpretation — not
  verified against the document"*.
- Withheld statements are reported as counts with a plain-language reason, and
  their text is never received by the browser.
- The UI never upgrades a status and falls back to the safer option on an
  unknown one.
- Extracted text and filenames are rendered as text, never as markup.

- The values panel lists amounts, dates and time periods with their page
  numbers, under a subtitle stating it is not a summary and not a risk
  assessment. It is a named landmark region, and needs no analysis to appear.

- The overview panel groups released findings under a closed list of document
  topics, so a reader can see the shape of what was established rather than an
  unordered list. It publishes nothing of its own: every claim, quote, page and
  citation in it is already in the findings below it, and a test asserts that
  strict-subset property at the endpoint. A topic with nothing under it says
  *"No verified finding was released for this category"* — a statement about
  what this analysis released, never about what the document contains, since
  the application cannot establish the absence of a clause. It is a named
  landmark region, carries no risk indicator and no ownership wording, and does
  not repeat the unverified explanation.

**Not rendered.** The `attention` level is present in the API response and in
the frontend's TypeScript types, but no component displays it. There is no
attention badge, risk chip or severity indicator in the interface. A user sees
clause findings, categories, claims, quotes, pages, confirmed citations,
labelled explanations and withheld counts — and nothing representing attention.

## 5. Not implemented

Named so their absence is not mistaken for an oversight. See
`docs/11_PROMPTWARS_ALIGNMENT.md` for how these relate to the problem statement.

| Item | Status |
|---|---|
| Two-document or multi-document comparison | Not implemented |
| Document summaries | Not implemented |
| Checklist generation | Not implemented |
| Export / download of findings | Not implemented |
| Options or next-steps guidance | Not implemented |
| Preparing a briefing pack for a legal professional | Not implemented |
| DOCX upload | Not implemented (rejected at validation) |
| OCR fallback for scanned pages | Not implemented — a page with images and no text layer blocks a complete-document analysis instead |
| Tamil / multilingual explanation | Not implemented; all vocabularies are English-only |
| Clause navigation, dark mode, document history | Not implemented |
| Authentication, accounts, persistence | Not implemented |

## 6. Known limitations that affect the product surface

1. **The explanation is not verified.** Contradiction gating on explanations
   was implemented in four variants and measured as unworkable; what shipped is
   value binding plus a UI label. This is a presentational control and weaker
   than verification.
2. **`attention` is API-only, and is not a risk assessment.** The backend
   derives an `attention` level in its API response, but the current frontend
   does not render this field; visual attention badges are not implemented.
   Where it is used, it counts features the quoted text contains and says
   nothing about whether a clause is onerous, unusual, unenforceable or unfair.
   Rendering it would be a UI feature change and is not claimed as done.
3. **A real citation can be dropped.** A heading living in a page header the
   extractor discarded is unconfirmable; the citation is dropped and the
   finding survives.
4. **Answer-level numeric granularity is blunt.** An unsupported figure
   anywhere in a multi-sentence answer withholds all of it.
5. **Three corpus cases remain undetected** — a restriction carried by a
   participle phrase, an item dropped from an enumerated exclusion, and a
   fabricated sentence reusing the evidence's vocabulary. Kept red in the test
   suite; §7 of `PHASE_15_REPORT.md` explains why no lexical rule separates them
   from legitimate paraphrase.
6. **Live validation is thin, not absent.** The output policy has run against
   live model output — two successful end-to-end runs through the real
   endpoints on 2026-09-22, releasing 2 of 9 and 1 of 9 proposed findings.
   The Phase 15 and Phase 16 evidence gap is closed. Repeatability is not:
   those two successes came from six live analysis attempts that day, the
   other four failing as a non-returning call, a reply with no parsable JSON,
   and two provider-capacity `503`s. No live recall figure exists, no live
   Q&A success has been observed, and the overview panel has not been
   rendered in a browser from a live analysis.
7. **The browser suite uses a stub backend and no CI runs it.**
8. **In-process job execution.** A restart loses running analyses, instances do
   not coordinate, and there is no backpressure. Fine for a demo; not
   production job processing.

## 7. Explicitly out of scope

- Legal representation or advice.
- Automated legal filing.
- Guaranteed legal correctness.
- Personalised legal recommendations.
- Autonomous communication with courts or lawyers.
- Payments, real-time collaboration, fine-tuning.
- Permanent document storage.
- A second LLM judging the first.
- Complex multi-agent swarm.
- External legal research substituted for the uploaded document.
- Vector database / RAG.

## 8. Core user flow

```text
Upload PDF
    ↓
Validate file
    ↓
Extract pages → per-page manifest
    ↓
Measure coverage (application, not model)
    ↓  complete only
Analyze with Nemotron
    ↓
Structured model proposal
    ↓
Deterministic evidence verification
    ↓
Claim-level semantic verification
    ↓
Injection / security checks
    ↓
Central output policy (release boundary)
    ↓
Verified findings shown; withheld counted
    ↓
Document-grounded Q&A
```

## 9. Accuracy model

Accuracy is not delegated to the LLM.

**Layer 1 — Model interpretation.** Nemotron identifies clauses and writes
plain-language claims and explanations. Its output is a *proposal*.

**Layer 2 — Deterministic evidence validation.** Page existence, quote
existence, text location, figures, dates, polarity, document identity,
extraction status.

**Layer 3 — Claim-level semantic verification.** Eight axes over closed
vocabularies, applied per sentence against the sentence its evidence sits in.

**Layer 4 — Output policy.** Citation confirmed or dropped, attention derived,
explanation judged, category bounded. Unsupported content is withheld entirely.

## 10. Long-document requirement

For a 50-page document the application maintains its own manifest:

```json
{ "expected_pages": 50, "processed_pages": 50, "failed_pages": [], "coverage_status": "complete" }
```

```json
{ "expected_pages": 50, "processed_pages": 30, "coverage_status": "incomplete" }
```

The system must not present a complete-document result when coverage is
incomplete, and the model's statement that it "read everything" is never
accepted as proof of coverage.

## 11. Functional requirements

| ID | Requirement | State |
|---|---|---|
| FR-01 | Reject unsupported, corrupted, oversized or malformed files | Implemented |
| FR-02 | Record document id, page count, extraction status, per-page state | Implemented |
| FR-03 | Prevent analysis when required pages failed ingestion | Implemented |
| FR-04 | Model output must conform to the application schema | Implemented |
| FR-05 | Every factual finding must carry document evidence | Implemented |
| FR-06 | Backend verifies evidence against the extracted content | Implemented |
| FR-07 | Validate dates, amounts, percentages, durations and counts | Implemented |
| FR-08 | Distinguish verified / partially verified / unverified / not found | Implemented |
| FR-09 | Treat instructions inside documents as untrusted content | Implemented |
| FR-10 | Do not persist documents | Implemented (ephemeral workspace, TTL, shutdown cleanup) |
| FR-11 | Keep document-specific answers scoped to the uploaded document | Implemented |
| FR-12 | Unsupported claims cannot be presented as verified facts | Implemented |
| FR-13 | Verify every model-supplied field a user sees, or drop it | Implemented (Phase 15), except `explanation` — see §6.1 |

## 12. Non-functional requirements

- Deterministic validation for critical fields.
- Traceable evidence beside every claim.
- Graceful, categorised failure with plain-language messages.
- Responsive UI.
- Server-side-only API keys; no secrets in frontend code.
- Reasonable latency for demo documents (a live model call is tens of seconds,
  which is why analysis is asynchronous).
- Accessibility-conscious design.

## 13. Success criteria

A demo is technically successful when:

1. A valid legal PDF can be uploaded.
2. The application establishes its own page count.
3. All pages reach a valid processing state, or the shortfall is surfaced.
4. The model produces structured findings.
5. Findings carry source evidence.
6. Evidence is independently checked.
7. Unsupported findings are withheld and counted.
8. Questions absent from the document produce a not-found response rather than
   invented facts.
9. The application survives malformed input and prompt-injection content.
10. The user can see why a finding was produced, and what was withheld.

## 14. Legal / safety disclaimer

The application provides legal *information* and document-understanding
assistance. It does not establish an attorney-client relationship, does not
replace professional legal advice, and does not guarantee legal correctness or
legal outcomes.
