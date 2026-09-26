# PromptWars Legal AI — System Architecture

**Status:** as-built, current as of Phase 15
**Architecture style:** controlled agentic workflow + deterministic verification + a single release boundary
**Primary LLM:** NVIDIA Nemotron 3 Nano Omni 30B-A3B Reasoning (hosted NVIDIA API)
**Agent framework:** LangChain (model abstraction) + LangGraph (workflow state machine)
**Backend:** FastAPI
**Frontend:** React + Vite + TypeScript + Tailwind CSS

> This document describes the architecture that exists. Where a design in an
> earlier revision was not built, it is marked **Not implemented**.

---

## 1. Architecture principle

The system is **agent-assisted, not agent-uncontrolled**.

The LLM is responsible for interpretation and reasoning. The application is
responsible for document completeness, evidence verification, deterministic
validation, state transitions, safety gates, and deciding what may reach the
user.

> **No model-generated factual claim reaches the user as verified unless the
> application can ground it in the uploaded document.**

## 2. The pipeline, as built

```text
React + Vite + TypeScript + Tailwind
                ↓
              FastAPI
                ↓
        LangChain / LangGraph
                ↓
      NVIDIA Hosted API
                ↓
 Nemotron 3 Nano Omni 30B-A3B
                ↓
       Structured Model Output
                ↓
 Deterministic Evidence Verification
                ↓
      Semantic Verification
                ↓
 Injection / Security Checks
                ↓
      Central Output Policy
                ↓
      Released User Output
```

Everything below the model is application code with no model dependency. The
verification layer imports no provider at all — a test asserts this — so
Nemotron, another vendor or a hand-written fixture all feed the same logic.

## 3. Component view

```text
┌───────────────────────────────────────────────────────────────┐
│                        React Frontend                         │
│  UploadPanel │ DocumentSummary │ CoveragePanel                │
│  AnalysisProgress │ FindingsPanel │ AskPanel │ Disclaimer     │
└───────────────────────────────┬───────────────────────────────┘
                                │ HTTP (dev: Vite proxy → :8000)
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                         │
│                                                               │
│  app/api/v1/    routes_health · routes_documents ·            │
│                 routes_analysis · routes_qa                   │
│      │                                                        │
│      ▼                                                        │
│  app/agents/    LangGraph state machine + in-process runner    │
│      │                                                        │
│      ├── app/documents/    validation · extraction ·          │
│      │                     manifest · storage · ingestion     │
│      ├── app/models/       provider · nemotron · prompts ·    │
│      │                     payload · errors                   │
│      └── app/verification/ coverage · grounding · numeric ·   │
│                            semantics · findings · qa ·        │
│                            policy · text                      │
└───────────────┬───────────────────────────────┬───────────────┘
                │                               │
                ▼                               ▼
     ┌─────────────────────┐        ┌──────────────────────────┐
     │  NVIDIA hosted API  │        │  Deterministic engine    │
     │  Nemotron 3 Nano    │        │  quote / page / value    │
     │  Omni Reasoning     │        │  polarity / semantics    │
     │  structured JSON    │        │  coverage / policy       │
     └─────────────────────┘        └──────────────────────────┘
```

## 4. The analysis workflow

`backend/app/agents/graph.py` is a LangGraph `StateGraph`, not an autonomous
agent:

```text
validate → ingest → coverage_gate → document_map → model → verify → output_gate
```

The model occupies exactly one node and chooses nothing about control flow. It
cannot call a tool, revisit a stage, or decide it has read enough.

Two routing rules give the graph its safety properties, and both live in the
graph's **edges** rather than inside a node that could lose them:

- A node that records a failure is never followed by another node.
- The only edge into `document_map` comes from `coverage_gate`, and the only
  edge into `model` comes from `document_map`. A document that fails coverage —
  `incomplete`, `failed`, `blocked_repaired`, or carrying unreadable pages —
  cannot reach the provider at all. Tests assert both the edge topology and the
  behaviour: the fake provider records zero calls.

Every node reuses the module that already implements its rule; no node
re-implements validation, extraction, coverage or verification.

### Job execution

`AnalysisRunner` runs the graph as an asyncio task and is the seam a real job
queue would replace. What it is **not**, stated plainly because it matters
before any multi-instance deployment:

- a restart loses running analyses (jobs live in process memory),
- instances do not coordinate (the duplicate-analysis lock is per-process),
- there is no backpressure,
- jobs are as ephemeral as the documents they belong to.

### Status and stage

`status` is `queued`, `running`, `completed` or `failed`; `completed` is set
only once the output gate has run. `stage` names the workflow step the run is
**entering**, so a client polling through a long model call reads `analyzing`.
Nothing routes on the reported stage.

## 5. Document lifecycle state

Two resources own the journey, so no state is tracked twice:

```text
DOCUMENT resource            ANALYSIS resource
validated                    queued
  ↓                            ↓
extracting                   running  (validating … gating_output)
  ↓                            ↓
ingested | ingestion_failed  completed | failed
```

`analysis_eligible` on the document status is the field a client acts on. The
backend enforces the same rule independently: a client that ignores it and
posts to `/analyze` gets a terminal analysis with `error_category:
"coverage_error"`, and no model call is made.

## 6. Components

### 6.1 Frontend

React 19 + Vite + TypeScript + Tailwind CSS v4. Components: `UploadPanel`,
`DocumentSummary`, `CoveragePanel`, `AnalysisProgress`, `FindingsPanel`,
`AskPanel`, `Disclaimer`; hooks `useAnalysis`, `useAsk`; a single typed API
client in `services/api.ts`.

The frontend performs exactly the documented sequence and nothing else. It
derives every label from backend values, never upgrades a status, and falls
back to the safer option on an unknown one. It never calls the model provider.

### 6.2 API layer

FastAPI, all routes under `/api/v1`: health, document upload / extract /
manifest / status / delete, analyze / analysis status / findings, and ask.
Every failure returns one error envelope with a stable machine-readable code
and a plain-language message — never a stack trace, provider exception text,
prompt, API key or internal path.

### 6.3 Document layer

MIME and signature validation, size and page limits, PDF parseability, page
counting, page-level text extraction via PyMuPDF, per-page manifest, ephemeral
per-document storage with TTL and shutdown cleanup.

**Not implemented:** DOCX extraction, OCR fallback, section detection as a
separate pass. Section labels come from the model's citation and are confirmed
against the cited page rather than detected structurally.

### 6.4 AI layer

- **LangChain** — model abstraction and the NVIDIA endpoint integration.
- **LangGraph** — the workflow state machine of §4.
- **Nemotron 3 Nano Omni** — document interpretation, clause identification,
  evidence candidate generation, plain-language explanation.

**No tools are exposed to the model.** The tool interfaces sketched in earlier
revisions of `03_AI_AGENT_SPEC.md` were not built, and the graph's safety
argument depends on the model having no tool access.

### 6.5 Verification layer

Deliberately non-LLM, in five modules:

| Module | Responsibility |
|---|---|
| `coverage.py` | The application's own coverage verdict and the hard gate |
| `grounding.py` | Evidence present → page exists → quote occurs → values agree |
| `numeric.py` | Currency, percentages, durations, quantities, dates, across multiple locale formats |
| `semantics.py` | Claim-level axes over closed vocabularies; injection, reported speech, definition conflicts |
| `findings.py` / `qa.py` | The two typed surfaces, over shared primitives |
| `policy.py` | The release boundary |

### 6.6 Storage

Ephemeral processing. An in-memory document store plus a per-document
workspace directory, deleted on discard, on TTL expiry and at shutdown. No
database, no permanent storage of uploaded documents.

## 7. Model abstraction

```text
ModelProvider (abstract)
    └── NemotronProvider   nvidia/nemotron-3-nano-omni-30b-a3b-reasoning
```

```python
class ModelProvider(ABC):
    async def analyze_document(self, request: AnalysisRequest) -> ModelAnalysis: ...
    async def answer_question(self, request: QuestionRequest) -> ModelAnswer: ...
```

`get_model_provider()` is the one decision point. A second provider is one
subclass and one line there.

**Not implemented:** the Gemini fallback provider sketched in earlier
revisions. There is exactly one provider today.

Provider security properties, each covered by a test: the API key is read from
settings only, never logged, never returned, and stripped from upstream error
text before it is raised; document content is sent inside an explicitly
labelled untrusted block with page markers neutralised; only pages the
application captured are sent; provider errors reach the client as safe
messages with stable codes; there is no automatic retry anywhere.

## 8. Finding and verification shape

```json
{
  "id": "f_001",
  "type": "termination",
  "claim": "Either party may terminate with 30 days written notice.",
  "evidence": { "page": 37, "section": "Termination", "quote": "30 days' written notice" },
  "explanation": "Either side can end the agreement with a month's notice.",
  "explanation_verified": false,
  "attention": "review",
  "verification_status": "verified"
}
```

`section` is present only when the cited page carries that exact label.
`attention` is derived by the application — and is returned by the API but
**not rendered by the current frontend**, so it is part of the contract rather
than a user-facing capability. `explanation_verified` states whether the
evidence establishes the explanation, and a client must not present an
unverified explanation as a fact.

## 9. The grounding gate

```text
model claim
   │
   ▼  evidence present? ── no ──► unverified
   ▼  page exists?      ── no ──► rejected
   ▼  quote occurs?     ── no ──► rejected
   ▼  values agree?     ── no ──► rejected
   ▼  polarity intact?  ── no ──► rejected
   ▼  claim semantically supported by its own evidence?
   │        contradicted ──► rejected
   │        unsupported  ──► unverified
   ▼  release policy: citation confirmed or dropped,
      attention derived, explanation judged, category bounded
   ▼
  VERIFIED (the only status shown as an established fact)
```

Each step can only lower a verdict. Nothing anywhere promotes one.

## 10. Long-document strategy

Context length is not treated as a correctness guarantee. The application
determines the page count itself, builds a manifest, extracts pages, confirms
coverage, builds the document map, calls the model, requires evidence for every
claim, and verifies against its own extracted content. It can prove which pages
were processed independently of the model's self-report.

## 11. Prompt injection defence

Uploaded document content is untrusted data. Defences, in layers:

1. Document content is sent inside an explicitly labelled untrusted block, and
   page markers occurring in document text are neutralised so a crafted PDF
   cannot close the block early.
2. The system prompt states that document text is never an instruction — a
   request, not a guarantee, and not relied on as a control.
3. The model has no tools, so there is nothing for injected text to invoke.
4. Text addressed to the assistant is **refused as evidence**, even though it
   genuinely occurs in the file. A claim resting on it therefore has no support.
5. Extracted text is rendered as text in the browser, never as markup.

## 12. Deployment

Prepared in Phase 23, **not deployed**. Full detail in `docs/12_DEPLOYMENT.md`.

```text
Frontend → Vercel (static Vite build; only VITE_API_BASE_URL)
Backend  → Render (Docker, exactly one instance: state is in process memory)
LLMs     → Gemini API (analysis, Q&A) · NVIDIA API (reasoning notes)
Database → Supabase, optional: metadata + released findings only, backend-only
```

The analysis workflow after Phase 23:

```text
validate → ingest → coverage_gate → document_map → model[ANALYSIS_PROVIDER]
        → verify → output_gate                      (release decided here)
        → reason[REASONING_PROVIDER] → reason_gate  (notes only; cannot touch findings)
```

## 13. Architecture decision records

Full reasoning and the Phase 10–15 decisions are in `docs/09_DECISIONS.md`.

### ADR-001 — Nemotron as primary model — *superseded by ADR-007 (Phase 23)*

Multimodal document intelligence positioning, OCR capability, reasoning, long
context, hosted API availability. Caveat: vendor benchmarks do not prove
superiority on this project's documents, and nothing here measures Nemotron's
accuracy.

### ADR-002 — LangChain + LangGraph orchestration — *in effect*

Controlled state transitions rather than a free-running autonomous agent.
Realised as a fixed seven-node graph with the model in one node and no tools.

### ADR-003 — Deterministic verification — *in effect, extended*

Structured model output does not guarantee semantic correctness. Extended in
Phases 10–14 with claim-level semantic verification, and in Phase 15 with a
single release boundary covering every model-supplied field.

### ADR-004 — No RAG for MVP — *in effect*

Single-document understanding does not need retrieval infrastructure, which
would add retrieval failure modes.

### ADR-005 — Ephemeral document processing — *in effect, amended Phase 23*

No permanent storage of uploaded legal documents, minimising privacy exposure.
Amendment: optional, backend-only metadata persistence (Supabase) may store
document metadata and **released** findings; PDFs, page text, raw filenames,
questions, answers and withheld output are never stored. See
`docs/09_DECISIONS.md`.

### ADR-006 — One release boundary (Phase 15) — *in effect*

A check that protects one surface and misses another is the defect class that
survived three phases. `app/verification/policy.py` is the single place where
"may this reach a user" is decided, and `build_result` may render only what it
produced. Enforced structurally: replace a control and the endpoint's response
must change.

### ADR-007 — Provider roles, no fallback (Phase 23) — *in effect*

Analysis and Q&A default to Gemini; reasoning notes use Nemotron. Each role is
configured separately and calls only its configured provider. A missing key is
a clean `not configured`, never a silent switch of vendor. Provenance records
the provider actually used.

### ADR-008 — Reasoning notes are not verification (Phase 23) — *in effect*

A second model reasoning over released findings is useful to a reader and
dangerous as an authority. Notes run after the release gate, see only released
findings, are gated for scope (ids, quotes, figures, instructions, legal
conclusions) and carry a fixed "not independently verified" label. They never
change a finding. This is not the "second LLM verifier" refused in
`docs/11_PROMPTWARS_ALIGNMENT.md` §5: nothing it says decides a release.
