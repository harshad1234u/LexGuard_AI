# PromptWars Problem Statement Alignment

**Status:** current as of Phase 21
**Purpose:** state, without inflation, how this project relates to the official
PromptWars problem statement.

This document is the single place where alignment is claimed. Every status
below was checked against the code, not against an earlier document. Where a
listed direction is not built, this document says so.

---

## 1. The official problem statement

> ### AI for Legal Assistance & Access
>
> Legal information can often be complex, difficult to understand, and
> challenging to navigate without professional assistance.
>
> Build a GenAI-powered solution that makes legal information and basic legal
> assistance more accessible by helping users understand, compare, and navigate
> legal documents and information.
>
> Potential use cases include:
>
> - Simplifying complex legal documents
> - Comparing contracts, agreements, or policies
> - Highlighting important clauses, obligations, risks, or inconsistencies
> - Answering questions based on provided legal documents
> - Helping users understand their options and potential next steps
> - Generating summaries, checklists, or other actionable outputs
> - Helping users prepare information or questions for a legal professional

The problem statement also states two things that govern how this document is
written:

1. Solutions should **provide information and assistance rather than replace
   professional legal advice**.
2. The listed use cases are **potential directions, not exhaustive and not
   prescriptive**. Participants are encouraged to explore the problem
   creatively and develop innovative or different use cases.

Point 2 is why the matrix below is not an implementation checklist. A direction
marked *Not implemented* is not a gap against the problem statement; it is a
direction this project chose not to take.

## 2. What this project is

> An evidence-grounded GenAI legal document intelligence system that helps
> users understand complex legal documents, identify important clauses and
> obligations, and ask questions based on uploaded documents, while
> independently verifying AI-generated findings against document evidence
> before release.

The differentiator, stated exactly:

> **The LLM interprets the document; the application independently verifies
> what the LLM says.**

The depth of this project is in that second clause. Rather than covering more
of the listed directions, the work went into the verification layer that
decides whether an AI-generated statement may be shown at all — a deterministic
evidence verifier, eight semantic axes over closed vocabularies, seven
evaluation corpora, and a single release boundary that every user-facing field
passes through.

## 3. What this project is not

It is not an AI lawyer, not a replacement for a lawyer, not legal advice, not
legally authoritative, not guaranteed to be legally correct, and not
production-grade legal decision-making software. Nothing measured in any phase
of this project establishes legal correctness, and no figure in any report is a
reliability claim about law.

The system provides **legal information** and **document understanding**. Where
it shows something as verified, that is a claim about grounding in the uploaded
document — not a claim about law.

## 4. Alignment matrix

Status labels are used strictly:

| Label | Meaning |
|---|---|
| **Implemented** | Built, wired to a user-facing surface, covered by tests |
| **Partially implemented** | A defined subset is built; the rest is absent and named below |
| **API-only** | Computed by the backend and returned by the API, but **not rendered by the frontend**. Not a user-facing capability |
| **Not implemented / Planned** | Not built. A possible direction, with no implementation today |
| **Explicitly excluded** | Deliberately out of scope, with a recorded reason |

| PromptWars direction | Status | What actually exists |
|---|---|---|
| Simplifying complex legal documents | **Partially implemented** | Each finding carries a one-sentence plain-language `claim`, verified claim-by-claim against its quoted evidence. A longer `explanation` is also returned, but it is **not** verified — it is labelled *"Interpretation — not verified against the document"* in the UI and carries `explanation_verified: false` in the API. See §6.1. |
| Comparing contracts, agreements, or policies | **Not implemented** | No multi-document capability exists. The workflow state, the coverage controller, the model payload and the verifier are all scoped to exactly one document. Recorded as a possible future direction; no code supports it. |
| Highlighting important clauses, obligations, risks, or inconsistencies | **Partially implemented** (clause findings) + **API-only** (`attention`) | **In the UI:** clause-level findings with a category (parties, term, termination, payment, fees, renewal, confidentiality, liability, indemnity, governing law, dispute resolution), each with its verified claim, quote and page, **grouped by document topic in the overview panel (Phase 21)** so a reader can navigate them rather than scan a flat list. **Not in the UI:** the backend derives an `attention` level of `info` / `review` / `high` and returns it in the API response, but the current frontend does not render this field — visual attention badges are not implemented. Where it is used, `attention` is derived by the application from features the verified quote demonstrably contains, and is explicitly **not a legal risk assessment**. Inconsistency detection covers one case: a term the document defines twice and differently, which causes the evidence to be refused rather than reported as an inconsistency finding. |
| Answering questions based on provided legal documents | **Implemented** | `POST /api/v1/documents/{id}/ask` answers one question from one uploaded document, through the same coverage gate, evidence verifier and claim-level semantic checks as analysis. When nothing verifies, the model's words are discarded and the application answers in its own voice. |
| Helping users understand their options and potential next steps | **Not implemented** | No options analysis, no next-steps generation, no recommendation of any kind. Deliberate: suggesting what a user should do next is closer to advice than to information, and nothing in this system could verify such a suggestion against the document. |
| Generating summaries, checklists, or other actionable outputs | **Not implemented** | Still no summary, no checklist, no export and no download endpoint. The Phase 21 overview groups released findings by topic and is **not** any of these: it contains no sentence about the document as a whole, and an empty topic reports what the analysis released rather than what the document contains. A summary is a claim spanning a whole document, while the verifier binds a claim to one evidence sentence; making summaries safe remains a verification problem this project has not solved. |
| Helping users prepare information or questions for a legal professional | **Not implemented** | No such feature exists. Possible future direction; nothing today. |

### Beyond the listed directions

The problem statement invites different use cases. This project's contribution
sits outside the seven bullets:

| Capability | Status | What it is |
|---|---|---|
| Application-measured document coverage | **Implemented** | The application counts pages itself and refuses a complete-document analysis unless every page was captured. The model is never asked, and never told, whether the document was fully read. |
| Deterministic evidence verification | **Implemented** | Every model-proposed quote is located in the document: page exists, quote occurs there, figures and dates agree, polarity intact. |
| Claim-level semantic verification | **Implemented** | Eight axes over closed vocabularies — polarity, modality, actor and role binding, conditions, certainty, scope, temporal direction, time limits — on both the findings path and the Q&A path, sharing one implementation. |
| Prompt-injection-resistant evidence handling | **Implemented** | Text addressed to the assistant inside a document is refused as evidence, even though it genuinely occurs in the file. |
| Deterministic value index | **Implemented** | Amounts, percentages, time periods and dates located in the document by the application itself, each bound to its page, with no model involved. It reports what the document *says*, never what it means — a value is not labelled a deadline, obligation or risk. Complements the verified-findings path: a reader can see the figures and periods even when the model proposes no finding about them, and it works when the provider is unavailable. |
| Single release boundary | **Implemented** | Every field the API publishes — claim, quote, citation, attention, category, explanation — is confirmed, derived by the application, or dropped, in one place no endpoint can route around. (Of these, `attention` is returned but not rendered by the current frontend.) |
| Tamil reading support (Phase 23) | **Partially implemented** | A labelled Tamil translation added beside checked English explanations and answers, released only when the original fully passed and its numerals match the evidence. Not semantically checked. Tamil polarity/modality semantics are **deferred**; other languages are **explicitly excluded**. |
| Reasoning notes across released findings (Phase 23) | **Implemented** (not verified by design) | A second model points out how released findings may relate. Labelled "not independently verified", gated for scope, unable to change a finding. It is interpretation to guide reading, not a verified output and not advice. **Not verified live.** |
| Provider provenance (Phase 23) | **Implemented** | Every result and answer records the provider and model actually used and the release-policy version. |
| Document overview (grouped navigation) | **Implemented** | Released findings grouped under a closed list of document topics, published on the findings response and rendered as a named landmark region. A strict projection: every claim, quote, page and citation in it is already in `result.findings`, asserted at the endpoint, and a structural test takes the release policy off the path and checks that the overview empties with the rest of the response. It calls no model, repeats no unverified explanation, renders no risk indicator, and states of an empty topic only that nothing was released for it. |

## 5. Explicitly excluded

Recorded so that absence is not read as oversight:

| Excluded | Reason |
|---|---|
| Legal advice, representation, or recommendations | The product provides information. Advice is outside its competence and outside its claims. |
| Guaranteed legal correctness | Nothing in this system measures legal correctness. |
| Automated filing, or communication with courts or lawyers | Out of scope for an informational tool. |
| A second LLM used to judge the first | Measured and refused: it replaces an auditable rule with an unauditable one (`docs/09_DECISIONS.md`). Phase 23's Nemotron reasoning notes are not this: they run after the release gate and decide nothing. |
| Vector database / RAG | Not needed for single-document understanding, and it adds retrieval failure modes (ADR-004). |
| Autonomous multi-agent swarm | The workflow is a fixed state machine; the model chooses nothing about control flow (ADR-002). |
| Permanent document storage | Ephemeral per-document workspace only (ADR-005). Phase 23's optional persistence stores metadata and released findings, never documents or page text. |
| Fine-tuning | Out of scope. |
| DOCX upload | The extraction path does not exist, so DOCX is rejected at validation rather than half-supported. |
| Chat history in Q&A | Earlier turns would be a second source of context the verifier cannot check. |

## 6. The honest edges

Three things a reader evaluating alignment should know, stated here rather than
buried.

### 6.1 The explanation is not verified

Four contradiction-gating rules were implemented and measured against 28
explanations; none was both safe and useful (2/20 false positives at best
recall, 6/8 attacks missed at best precision). What shipped is the part that
works — figures in an explanation must appear in the evidence, at 0/20 measured
false positives — plus a UI label and an API field. That is a presentational
control, weaker than verification, and the documentation says so rather than
implying the field is checked.

### 6.2 The output policy has run live, twice, and that is all it has done

Provider capacity (`503 ResourceExhausted`) blocked the live reading during
Phase 15 and again during Phase 16, and both reports record the gap as open.
It is now closed. Two runs on 2026-09-22 drove the real `NemotronProvider`
through the real endpoints on the demo contract and reached the output policy
with real model output:

| | Model call | Proposed | Evidence check | Claim check | Output policy |
|---|---|---|---|---|---|
| Phase 19 validation | ok, 127,703 ms | 9 | 8 verified, 1 rejected | 6 withheld | **released 2, withheld 7** |
| Phase 21 validation | ok, 114,675 ms | 9 | 1 verified, 4 rejected, 4 unverified | — | **released 1, withheld 8** |

In the Phase 21 run the released finding was also checked through the document
overview, and the strict-projection invariant held: 1 overview item, 0 items
absent from the released findings.

Three things that closure does **not** establish, stated because the
distinction is the whole point of this section:

1. **Repeatability is unmeasured.** Those two successes came from six live
   analysis attempts on the same day. The other four failed as a call that
   never returned (18.7 minutes, no provider log line), a reply of 7,264
   characters containing no parsable JSON, and two provider-capacity `503`s.
   Two of six is not a reliability figure and is not quoted as one.
2. **Live recall is unmeasured.** Nothing here says how much of a document a
   live model finds, or how much of what it finds survives verification. The
   corpora measure the application's grounding boundary, not the model.
3. **Two live paths remain unvalidated.** A live Q&A *success* has not been
   observed end to end, and the overview panel has not been rendered in a
   browser from a live analysis — two attempts were blocked by the provider.

### 6.3 `attention` is API-only

The backend derives an `attention` level in its API response, but the current
frontend does not render this field. User-facing clause findings and categories
are available; visual attention badges are not implemented.

The Phase 15 work on this field was a **security** fix and it holds: a risk
level chosen by the model can no longer reach a response, because the
application derives the value itself. What that work did not do is surface the
value in the interface. A reader of the UI sees clause findings, categories,
claims, quotes and pages — not an attention badge.

Rendering it would be a UI feature change, and it is not claimed as done. Until
it is, this field must be described as API-only rather than as a user-facing
risk indicator.

### 6.4 The corpora are not a sample of contracts in the wild

286 cases across seven corpora. Some are built on real public-domain and
public-filing text — verbatim US Federal Acquisition Regulation clauses, SEC
EDGAR exhibits, EU Decision 2021/914 — but every adversarial variant is a
transformation this project applied to that language, and the remaining corpora
were written here. Three cases remain undetected and are kept red in the test
suite. None of it measures Nemotron's accuracy; it measures the application's
grounding boundary.

Full limitation registry: `docs/04_SECURITY_GROUNDING.md` §7b,
`PHASE_15_REPORT.md` §11 and §13.
