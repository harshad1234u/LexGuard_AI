# LexGuard AI

**PromptWars problem statement:** *AI for Legal Assistance & Access*

An evidence-grounded GenAI legal document intelligence system. It helps people
understand complex legal documents, identify important clauses and obligations,
and ask questions about an uploaded document — and it independently verifies
the model's claims against that document before any of them reach the user as
fact.

The defining property of the system:

> **The LLM interprets the document; the application independently verifies
> what the LLM says.**

It provides legal *information* and document understanding. It is not an AI
lawyer, not a replacement for legal advice, not legally authoritative, and not
production-ready. Nothing measured in this project establishes legal
correctness.

## Architecture

```text
React + Vite + TypeScript + Tailwind
                ↓
              FastAPI
                ↓
        LangChain / LangGraph
                ↓
  Gemini (analysis + Q&A, default)
  Nemotron (reasoning notes, post-release)
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
verification layer imports no provider at all — a test asserts this.

The full specification lives in [`docs/`](docs/). Those documents are the
source of truth; `docs/09_DECISIONS.md` lists the frozen architecture
decisions, and `docs/11_PROMPTWARS_ALIGNMENT.md` states how this project
relates to the problem statement.

## Alignment with the problem statement

The problem statement lists seven potential use cases and says explicitly that
they are directions, not a specification — not exhaustive, not prescriptive.
This project covered fewer of them and verified what it covered.

| PromptWars direction | Status |
|---|---|
| Simplifying complex legal documents | **Partially implemented** — verified plain-language claims; the longer explanation is labelled interpretation, not verified |
| Comparing contracts, agreements, or policies | **Not implemented** |
| Highlighting important clauses, obligations, risks, inconsistencies | **Partially implemented** — clause findings and categories are shown in the UI. The backend derives an `attention` level and returns it in the API, but the frontend does not render it, so visual attention badges are **not implemented**. Inconsistency detection limited to conflicting definitions |
| Answering questions based on provided legal documents | **Implemented** |
| Helping users understand options and next steps | **Not implemented** |
| Generating summaries, checklists, actionable outputs | **Not implemented** |
| Preparing information/questions for a legal professional | **Not implemented** |

The reason is uniform across the five not implemented: each is a claim the
verifier cannot bind to one evidence sentence. Shipping them unverified would
contradict the one property this product exists to demonstrate. Full matrix and
reasoning: [`docs/11_PROMPTWARS_ALIGNMENT.md`](docs/11_PROMPTWARS_ALIGNMENT.md).

## Current status

| Phase | Scope | State |
|---|---|---|
| 1 | Repository and environment setup | Done |
| 2 | Document upload + validation | Done |
| 3 | PDF extraction + page manifest | Done |
| 4 | Coverage controller | Done |
| 5 | Deterministic evidence verification | Done |
| 6 | Nemotron API integration | Done |
| 7 | LangChain/LangGraph controlled workflow | Done |
| 8 | End-to-end upload → analyze → verify → display | Done |
| 9 | Document-grounded Q&A | Done |
| 10 | Security, semantic grounding and evaluation hardening | Done |
| 11 | Evaluation expansion and false-positive analysis | Done |
| 12 | Real-contract validation and role binding | Done |
| 13 | Cross-domain validation and named-entity role safety | Done |
| 14 | Independent adversarial validation and security hardening | Done |
| 15 | Structural safety, end-to-end coverage and release hardening | Done |
| 23 | Gemini + Nemotron provider roles, reasoning notes, Tamil translations, optional Supabase metadata, deployment prep | Done against stubs; live validation blocked by Gemini quota exhaustion in Phase 24 (all safety invariants verified by test) — see [`docs/PHASE_24E_FINAL_GEMINI_PRODUCTION_GATE_REPORT.md`](docs/PHASE_24E_FINAL_GEMINI_PRODUCTION_GATE_REPORT.md) |

**MVP demo-ready with documented limitations.** Not production-ready, not
legally accurate, and nothing here establishes either — see
[Limitations](#limitations).

Implemented endpoints:

```text
GET    /api/v1/health
GET    /api/v1/ready
POST   /api/v1/documents/upload
POST   /api/v1/documents/{id}/extract
GET    /api/v1/documents/{id}/manifest
GET    /api/v1/documents/{id}/values
GET    /api/v1/documents/{id}/status
DELETE /api/v1/documents/{id}
POST   /api/v1/documents/{id}/analyze
GET    /api/v1/analysis/{id}/status
GET    /api/v1/documents/{id}/findings
POST   /api/v1/documents/{id}/ask
```

`/values` is a deterministic index of the amounts, percentages, periods and
dates the document contains, bound to their pages. No model is involved, so it
works when the provider does not — and it reports what the document *says*,
never what it means. A value is not a deadline, an obligation or a risk;
establishing that is interpretation, and interpretation goes through
`/findings`.

There is no summary, comparison, checklist or export endpoint.

PDF only. DOCX is rejected at validation rather than half-supported, because
its extraction path does not exist.

## Document-grounded Q&A

```text
question -> coverage gate -> model -> Phase 5 verifier -> Q&A gate -> answer
```

`POST /documents/{id}/ask` answers one question from one uploaded document.
**Synchronous** — a person is waiting for a short answer, so there is no job to
poll; `QA_TIMEOUT_SECONDS` (default 120) bounds the held connection.

It reuses the same gates as analysis rather than adding parallel ones. Each
quote the model offers becomes the `Finding` shape the Phase 5 verifier already
judges, carrying the **answer text** as the claim — so the existing numeric,
currency and date comparison runs against what the user is actually being told.
An answer that says "90 days" while quoting a page that says 30 is rejected by
the same code that rejects it for a finding.

The safety gate has one hard rule:

> The model's answer text is released **only** when at least one of its quotes
> verified against this document.

When nothing verifies, the model's words are discarded and the application
answers in its own voice: *"I couldn't find this information in the uploaded
document."* That wording is deliberate — it reports that nothing could be
confirmed, never that the clause does not exist.

Not a chatbot: no history, no persona, no memory between questions. Carrying
earlier turns would give the model a second source of context the verifier
cannot check.

## Claim-level grounding

Phase 10 measured the Phase 9 boundary and found a gap. Verifying that a quote
exists and that its numbers agree does **not** establish that the prose built
on it means the same thing. Against

> "The employee must not disclose confidential information."

the answer *"The employee may disclose confidential information."* passed every
check, because no number was in dispute. Four of eight adversarial cases were
released as `supported`.

The answer is now split into sentences and each is checked against the sentence
its evidence sits in, on eight axes where legal effect turns on a closed
vocabulary:

| Axis | Caught |
|---|---|
| Polarity | a dropped or added negation, including prohibition phrased without "not" |
| Modality | permission vs obligation vs prohibition (`may` → `must`) |
| Actor | a party absent from the evidence, and role reversal between vocabulary parties or named companies |
| Conditions | a conditional right presented as an absolute one |
| Certainty | an option restated as automatic ("may be renewed" → "will automatically renew") |
| Scope | a restriction dropped or broadened ("some services" → "all services") |
| Temporal direction | "before termination" → "after termination" |
| Time limits | a date or period restated as open-ended |

A sentence the evidence does not establish is removed from the answer and
counted; a sentence that restates the evidence with a flipped modal or a
dropped negation withholds the whole answer.

> A verified quote does not make every sentence beside it verified.

Evidence is also refused when it is text addressed to the assistant, when it
merely *points* to a definition or schedule rather than stating its contents,
when it records reported speech rather than a term of the agreement, or when
the document defines the same term twice and differently.

No second LLM was added. The failure modes turned out to be deterministic, and
a model-based judge would replace an auditable rule with an unauditable one —
see `docs/09_DECISIONS.md`.

### Measuring it

```bash
cd backend && .venv/Scripts/python eval_harness.py --corpora      # all corpora, separately
cd backend && .venv/Scripts/python eval_independent.py            # the independent corpus
cd backend && .venv/Scripts/python eval_independent.py --mutations
```

Seven corpora, 286 cases, run through the real verification stack and
**reported separately, never averaged** — because a verifier that refuses
everything has a perfect false-negative rate and is useless, so both error
types always appear together.

```text
REALISTIC / FAR          attacks 14/14   legit 12/12   verbatim FAR clauses
REALISTIC / CROSS-DOMAIN attacks 28/28   legit 24/24   SEC EDGAR + EU Decision 2021/914
NAMED ENTITY             attacks 15/15   legit 16/16
DEFINITIONS              attacks  9/9    legit  6/6
ROLE REVERSAL            attacks 12/12   legit  8/8
SEMANTIC                 attacks 39/39   legit 28/28
INDEPENDENT (75 cases)   detection 94.2% (49/52)   false positives 0.0% (0/20)
MUTATIONS                98.8% (85/86)
```

Only the realistic corpora use language nobody on this project wrote. **The
synthetic figures are optimistic by construction** — those checks were
developed against those cases — and are not independent validation. No model is
called for any of this; it measures the application's grounding boundary, not
Nemotron's accuracy.

A 100% score has already been shown to mean fit rather than reliability: Phase
13 scored 14/14 on FAR text and then caught 15 of 28 on unfamiliar drafting,
and Phase 14's independent corpus dropped a 100% verifier to 90.4%. Both were
the most useful results of their phase.

Three cases remain undetected and are kept red in
`tests/test_independent_corpus.py::KNOWN_MISSES`, which fails if one starts
passing — so a future fix must be acknowledged rather than absorbed.

## Verification on both surfaces (Phase 14)

Everything above described Q&A, and until Phase 14 that was literally true:
claim-level semantic verification guarded question answering only. The findings
list — the product's primary surface — ran evidence checks alone. A finding
whose claim reversed its own quote was returned as `verified`, under a green
badge, with the contradicting quote printed underneath.

`app/verification/findings.py` closed this by running the **same**
implementations the Q&A gate runs, rather than a second copy of the rules, so
the two surfaces cannot drift apart. A test asserts identity, not equivalence:

```python
assert findings_module.check_answer is qa_module.check_answer
```

The root cause was architectural: there was no single place where "may this
reach a user" was decided. Phase 14 added the missing call; Phase 15 added the
place.

## The release boundary (Phase 15)

A finding that passes every claim check still carries four more fields, and
none of them was verified. Measured on the real workflow, a finding whose claim
was verbatim correct was released under a green ✓ Verified badge citing
*"Section 99.4 (Unrestricted Disclosure Permitted)"* — a section the document
does not have.

`app/verification/policy.py` is now the release boundary. Everything the
findings endpoint publishes comes from it, and the Q&A path shares its citation
check:

| Field | Rule |
|---|---|
| `section` | Confirmed by whole-label containment against the cited page, or dropped. A fabricated citation is worse than a fabricated sentence — it is the part a reader cannot check without the document. |
| `attention` | Derived by the application from features the verified text demonstrably contains. Never the model's choice, and **not a legal risk assessment**. Returned by the API; **not rendered by the current frontend**. |
| `explanation` | Values must appear in the evidence; an instruction is refused; otherwise released with `explanation_verified` stating whether the evidence establishes it. |
| `type` | Bounded in length and refused if it reads as an instruction. |

A run that never reached the boundary publishes nothing rather than falling
back on the model's proposal. Sixteen structural tests enforce the wiring by
substitution: replace a control, and the endpoint's response must change.

**What is deliberately not checked, and why.** Contradiction gating on
explanations was implemented in four variants and measured against 28
explanations; none was both safe and useful (2/20 false positives at best
recall, 6/8 missed at best precision). The residual risk is handled by
presentation — the UI labels an unverified explanation as interpretation —
which is weaker than verification and is recorded as such.

## The end-to-end journey

```text
upload -> status -> extract -> status -> analyze -> poll -> findings
```

`backend/tests/test_end_to_end.py` drives exactly this sequence through the public API,
including the paths that must stop: a scanned page, a document analysed without extraction,
an oversized upload, a provider failure, and a run where nothing survives verification.
The frontend performs the same sequence and nothing else.

Two resources own the journey, so no state is tracked twice: the **document** resource
owns validation and extraction (`validated` → `extracting` → `ingested` |
`ingestion_failed`), and the **analysis** resource owns everything from the coverage gate
onward (`AnalysisStatus` + `AnalysisStage`). The frontend reads `analysis_eligible` from
the document status and never computes coverage itself; the backend enforces the same rule
independently, so ignoring that field buys a `coverage_error`, not an analysis.

## The coverage rule

`coverage_status` is computed by `backend/app/verification/coverage.py` from the
application's own per-page counters. The model is never asked, and never told, whether the
document was fully read.

`complete` — the only verdict that permits a complete-document analysis — requires **all** of:

- `total_pages > 0`
- every page processed (blank pages count; they held nothing to miss)
- `failed_pages == []`
- no unreadable pages — a page with images but no text layer is almost always scanned, so
  its content was *not* captured
- `is_repaired == false`

That last condition is why a truncated PDF can report 50 of 50 pages processed and still be
`blocked_repaired`: PyMuPDF rebuilt the page count itself, so "every page we could see" says
nothing about how many pages the original had.

`require_complete_coverage()` is the hard gate. From Phase 7, the model is not invoked for a
complete-document analysis unless it passes.

## Evidence verification

`backend/app/verification/grounding.py` judges every model-proposed finding against the
document, deterministically. The chain is
`evidence present? -> page exists? -> quote occurs there? -> values agree?`, and each step can
only lower the verdict.

Statuses: `verified`, `partially_verified`, `rejected`, `unverified`. Only `verified` may be
shown to a user as an established fact; `VerificationResult.is_displayable_as_fact` is the
single place that rule lives.

Two guards stop a textually-similar quote from passing as the real thing:

- **Values** — every number, amount, percentage, duration and date in the quote must be
  present in the matched region. "30 days" and "60 days" are textually close and legally
  opposite. Continental (`€1.400.000,00`), Indian (`₹10,00,000`) and parenthesised-numeral
  (`forty-five (45) days`) formats are all handled; the first of those once parsed as
  `1.400`, a 1000× understatement that verified.
- **Polarity** — a difference in meaning-inverting words (`not`, `never`, `without`,
  `unless`, ...) rejects the match. Inserting one "not" is a tiny edit and a total reversal.

Values are bound to the evidence sentence cited for a claim, not merely to the page, so a
figure lifted from one clause cannot support an assertion about another.

The verifier depends on no model. It takes a `Finding` and anything satisfying the
`EvidenceSource` protocol, so Nemotron, another vendor or a hand-written fixture all feed the
same logic.

## Running it

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cp ../.env.example .env        # then fill in GEMINI_API_KEY (required) and NVIDIA_API_KEY (for reasoning)
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to port 8000
```

### Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # 1757 pass, 1 skip, offline (6 live tests deselected by default)
cd frontend && npm run test:e2e                       # 34 browser flows, stub backend
```

All backend tests are deterministic and offline — they mock model output rather than calling
the NVIDIA API (`docs/06_EVALUATION_PLAN.md`). Three independent mechanisms stop the default
suite from reaching a real key.

## Security notes

- `GEMINI_API_KEY` and `NVIDIA_API_KEY` are server-side only. The browser never contacts any model provider; all AI
  traffic is proxied through the backend.
- Uploaded documents are processed in an ephemeral per-document workspace and deleted on
  discard, on TTL expiry, and at shutdown. Nothing is stored permanently.
- Uploaded document content is untrusted data. Instructions found inside a document are never
  treated as instructions to the system — and, since Phase 10, text addressed to the
  assistant is **refused as evidence** even though it genuinely occurs in the file.
- The model has no tools, so injected text has nothing to invoke.
- Logs record ids, counts and question *length* — never document text, the question, the
  answer, or a quote.
- **No authentication and no application-level rate limiting.** The deployment is demo-only;
  both are required before any public one (`docs/04_SECURITY_GROUNDING.md` §10).

## Limitations

Stated here rather than buried, because the project's argument depends on being
accurate about its own boundaries.

- **Not production-ready.** The browser suite is not in CI — this repository has no CI
  configuration of any kind — and live provider reliability is poor enough that no
  availability claim is made (see below).
- **Live validation is thin, not absent.** The output policy *has* now run against live
  model output: two successful end-to-end runs through the real endpoints on 2026-09-22
  released 2 of 9 and 1 of 9 model-proposed findings respectively, with the remainder
  withheld by verification. That closes the evidence gap Phase 15 and Phase 16 recorded as
  open. What it does **not** establish is repeatability: those two successes came from six
  live analysis attempts the same day, the other four failing as a non-returning call, a
  reply containing no parsable JSON, and two provider-capacity `503`s. Live recall and
  repeatability remain unmeasured, a live Q&A *success* has not been observed, and the
  document overview has not been rendered in a browser from a live analysis.
- **Not legally accurate.** Nothing here measures legal correctness, and the system has no
  view on whether a clause is fair, enforceable or complete.
- **The explanation is not verified.** It is labelled as interpretation in the API
  (`explanation_verified`) and in the UI. A label is weaker than a check.
- **`attention` is API-only, and is not a risk assessment.** The backend derives it and the
  API returns it, but the current frontend does not render this field — visual attention
  badges are not implemented. Where it is used, it counts features the quoted text contains
  and says nothing about whether a clause is onerous, unusual, unenforceable or unfair.
- **A real citation can be dropped** when its heading lives in a page header the extractor
  discarded. Costs a citation, keeps the finding.
- **Not a general reliability figure.** 286 cases — some built on real public-domain and
  public-filing text, but with every adversarial variant written here — are not a sample of
  contracts in the wild.
- **Three adversarial cases remain undetected**, all of a shape no lexical rule separates
  from legitimate paraphrase.
- **English only.** Every vocabulary is English.
- **In-process job execution.** A restart loses running analyses, instances do not
  coordinate, and there is no backpressure. Background execution, not durable job
  processing.
- **Not checked at all:** anaphora, causation, cross-clause reasoning, definitional
  substitution, and scope or temporal reach beyond the closed vocabularies above. Claims
  resting on these are treated as unsupported rather than guessed at.

The full registry is in `docs/04_SECURITY_GROUNDING.md` §7b and §14, and
`PHASE_15_REPORT.md` §11 and §13.

## What the system actually demonstrates

Stated exactly, because a looser version of this sentence would be a claim the
project cannot support:

> Where the application shows a statement as verified, deterministic checks have
> confirmed that the quoted text occurs in the uploaded document at the cited
> page; that the figures and dates in the statement appear in the evidence cited
> for it; that the statement does not differ from that evidence in polarity,
> modality, actor, scope, conditionality, exceptions or temporal direction over
> the closed vocabularies those checks cover; that any section reference shown
> appears on that page; and that the attention level and category **returned by
> the API** were derived by the application rather than supplied by the model.
> Where any of that cannot be established, nothing is shown. The plain-language
> explanation beneath a finding is **not** covered by this and is labelled
> accordingly.

Two clarifications this sentence depends on: `attention` is returned by the API
but not rendered by the current frontend, so it is not among the things a user
sees; and the wording above is adapted from `PHASE_15_REPORT.md` §15, which
states the same property as it stood at that phase.

That is a claim about grounding. It is not a claim about law.

## Model providers (Phase 23)

`backend/app/models/` holds the only code that knows Google or NVIDIA exist.
Each responsibility is configured separately, and **nothing falls back**: a
role calls exactly the provider named for it, or reports itself not configured.

| Role | Setting | Default | Provider class | Output |
|---|---|---|---|---|
| Document analysis | `ANALYSIS_PROVIDER` | `gemini` | `GeminiProvider` (`google-genai`) or `NemotronProvider` | Proposed findings → verifier → release gate |
| Document Q&A | `QA_PROVIDER` | `gemini` | same choice | Proposed answer → verifier → answer gate |
| Reasoning notes | `REASONING_PROVIDER` + `REASONING_ENABLED` | `nemotron` | `NemotronProvider` | Notes about how **released** findings relate — labelled *"not independently verified"*, never a finding |

The application — not either model — decides what is verified. Gemini output
passes the same unchanged verifier and release gate Nemotron's did. Nemotron's
reasoning stage runs only after the release gate, sees only released findings,
and cannot change, add or remove one. Every result carries `provenance`
recording the provider actually called. Configuration, the no-fallback rule
and deployment are in [`docs/12_DEPLOYMENT.md`](docs/12_DEPLOYMENT.md).

**Tamil:** a reader may ask for Tamil. Claims, quotes and the checked
explanation or answer stay in the document's language; a Tamil translation is
*added* beside them, labelled "not independently checked", only when the
original fully passed and every numeral in the translation appears in the
evidence. Tamil semantic checks do not exist — see the Phase 23 report.

The verification layer imports no provider at all - a test asserts this.

Model output is a **proposal**. `analyze_document()` returns a `ModelAnalysis`,
which goes to `verify_finding()` before any of it can be shown as fact.
Adversarial and malformed model output is covered by 34 tests: empty,
truncated, prose-wrapped, fenced, wrong types, oversized, script tags, SQL,
null bytes, path traversal — and self-declared fields such as `verified`,
`confidence` and `risk_level`, which are dropped at parse and unreadable
thereafter.

Security properties, each covered by a test:

- The API key is read from settings only, never logged, never returned, and
  stripped from upstream error text by `redact()` before it is raised or logged.
- Document content is sent as a user turn inside an explicitly labelled
  untrusted block; page markers occurring in document text are neutralised so a
  crafted PDF cannot close the block early.
- Only pages the application actually captured are sent, addressed by the same
  page numbers the verifier uses.
- Provider errors reach the client as safe messages with stable codes; vendor
  detail and response bodies never do.
- There is no automatic retry. A metered API is not retried in a loop.

### The live tests

Live calls exist in `tests/test_nemotron_live.py` and
`tests/test_nemotron_live_phase14.py`, marked `live` and deselected by default.
Run them deliberately:

```bash
cd backend && .venv/Scripts/python -m pytest -m live
```

Verified live in Phase 15: a grounded question, an unsupported question, prompt
injection in document text, and a provider failure with a safe message. **Not
verified live:** structured extraction through the Phase 15 output policy — the
endpoint returned `503 ResourceExhausted` on every attempt that session. Live
tests skip with a reason on unavailability, rate limiting and timeout; an auth
failure or a malformed response still fails.

## The analysis workflow

`backend/app/agents/` holds a LangGraph state machine, not an autonomous agent:

```
validate -> ingest -> coverage_gate -> document_map -> model -> verify -> output_gate
```

The model occupies exactly one node and chooses nothing about control flow. It
cannot call a tool, revisit a stage, or decide it has read enough.

Two routing rules give the graph its safety properties, and both live in the
graph's **edges** rather than inside a node that could lose them:

- A node that records a failure is never followed by another node. There is no
  path on which a later stage works on unusable state.
- The only edge into `document_map` comes from `coverage_gate`, and the only
  edge into `model` comes from `document_map`. A document that fails coverage -
  `incomplete`, `failed`, `blocked_repaired`, or carrying unreadable pages -
  cannot reach the provider at all. Tests assert both the edge topology and the
  behaviour: the fake provider records zero calls.

Every node reuses the phase that already implements its rule. No node
re-implements validation, extraction, coverage or verification.

### The output gate

`is_displayable_as_fact` decides what survives verification; the release policy
decides what a client sees. Findings that fail verification are counted in
`result.withheld` and their text is never returned - not softened, not hedged,
not given a confidence score. When the model proposes findings and none
survive, the result says `insufficient_evidence: true`.

### Asynchronous by necessity

A real Nemotron call took ~37 seconds for one page, so no HTTP request waits for
the model:

```
POST /api/v1/documents/{id}/analyze   -> 202 + analysis_id
GET  /api/v1/analysis/{id}/status     -> stage, coverage, counts, error category
GET  /api/v1/documents/{id}/findings  -> the gated result (409 until complete)
```

Repeating the POST while an analysis is queued, running or completed returns the
existing one (`reused: true`) rather than buying a second inference. A *failed*
analysis starts a new run - retryable, but only because the user asked again.
There are no automatic retries anywhere in the system.

`AnalysisRunner._spawn` is the seam a real job queue would replace. Today it is
an asyncio task, which is the right size for ephemeral documents and no
database.

While a run is in flight, `stage` reports the step the workflow is **entering**,
not the one it just finished — so a client polling through a 37-second model
call reads `analyzing`, which is what is actually happening. The graph is
streamed for this; nothing routes on the reported stage.

### What the in-process runner is not

It is background execution, not durable job processing, and the difference
matters before this is deployed on more than one instance:

- **A restart loses running analyses.** Jobs live in process memory. A deploy,
  a crash or a reload drops anything in flight, and the client polling it will
  get a 404 rather than a result. Nothing is replayed.
- **Instances do not coordinate.** The duplicate-analysis rule holds within one
  process: `submit()` claims a document under a lock, so a double-clicked
  button buys one inference. Two instances behind a load balancer each keep
  their own job table and would each start a run for the same document. There
  is no shared lock, and adding one is a queue's job, not this class's.
- **There is no backpressure.** Concurrent analyses are bounded by nothing but
  the event loop. A real queue would cap in-flight work and meter provider
  calls.
- **Jobs are as ephemeral as the documents.** They are dropped when the
  document is discarded and when the process exits, by design (ADR-005).

Replacing `_spawn` and the job store with a real queue addresses all four. The
API, the graph and the gates do not change.

## Disclaimer

This application provides legal *information* and document-understanding assistance. It does
not create an attorney-client relationship, does not replace professional legal advice, and
does not guarantee legal correctness or outcomes.
