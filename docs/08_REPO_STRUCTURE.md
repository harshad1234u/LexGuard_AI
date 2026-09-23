# PromptWars Legal AI — Repository Structure

**Status:** as-built, current as of Phase 15. This is the actual tree, not a
proposal.

```text
promprtwar/
│
├── backend/
│   ├── app/
│   │   ├── main.py                     FastAPI app, middleware, lifespan cleanup
│   │   ├── api/v1/
│   │   │   ├── router.py               mounts the four route modules
│   │   │   ├── routes_health.py        GET /health
│   │   │   ├── routes_documents.py     upload · extract · manifest · status · delete
│   │   │   ├── routes_analysis.py      analyze · analysis status · findings
│   │   │   └── routes_qa.py            ask
│   │   ├── core/
│   │   │   ├── config.py               settings from environment only
│   │   │   ├── errors.py               error codes and the safe envelope
│   │   │   └── logging.py              structured, redacting logger
│   │   ├── documents/
│   │   │   ├── validation.py           filename · size · extension · MIME · signature · parseability
│   │   │   ├── extraction.py           PyMuPDF page extraction, per-page status
│   │   │   ├── manifest.py             the application's own processing record
│   │   │   ├── ingestion.py            extraction → manifest wiring
│   │   │   └── storage.py              ephemeral per-document workspace, TTL, cleanup
│   │   ├── agents/
│   │   │   ├── graph.py                the seven-node LangGraph state machine
│   │   │   ├── nodes.py                one node per workflow step; the output gate
│   │   │   ├── state.py                AnalysisState, including release_outcome
│   │   │   └── runner.py               in-process asynchronous job execution
│   │   ├── models/
│   │   │   ├── __init__.py             get_model_provider() — the one decision point
│   │   │   ├── provider.py             abstract ModelProvider + defensive JSON parsing
│   │   │   ├── nemotron.py             NemotronProvider (the only provider)
│   │   │   ├── prompts.py              the model's contract, untrusted-content framing
│   │   │   ├── payload.py              captured pages only, page markers neutralised
│   │   │   └── errors.py               provider error taxonomy, redaction
│   │   ├── verification/
│   │   │   ├── coverage.py             the coverage verdict and the hard gate
│   │   │   ├── grounding.py            evidence → page → quote → values
│   │   │   ├── numeric.py              currency · percentages · durations · dates, multi-locale
│   │   │   ├── semantics.py            claim axes, injection, reported speech, definitions
│   │   │   ├── findings.py             claim verification on the analysis path
│   │   │   ├── qa.py                   the Q&A gate
│   │   │   ├── policy.py               THE RELEASE BOUNDARY
│   │   │   └── text.py                 normalisation and matching primitives
│   │   └── schemas/
│   │       ├── documents.py  extraction.py  findings.py  analysis.py  qa.py  errors.py
│   ├── tests/                          ~40 modules; fixtures_*.py hold the corpora
│   ├── experiments/role_binding.py     the measurement behind "no NLP dependency"
│   ├── eval_harness.py                 corpora runner
│   ├── eval_independent.py             independent corpus + mutations
│   ├── eval_report.py                  reporting helper
│   ├── requirements.txt
│   ├── pytest.ini                      addopts = -m "not live"
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                     the whole journey, one screen
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── UploadPanel.tsx         DocumentSummary.tsx   CoveragePanel.tsx
│   │   │   ├── AnalysisProgress.tsx    FindingsPanel.tsx     AskPanel.tsx
│   │   │   └── Disclaimer.tsx
│   │   ├── hooks/                      useAnalysis.ts · useAsk.ts
│   │   ├── services/api.ts             the only place that talks to the backend
│   │   └── types/api.ts                the API contract, typed
│   ├── e2e/                            Playwright suite + stub backend + fixtures
│   ├── playwright.config.ts            starts both servers on private ports
│   ├── vite.config.ts                  dev proxy /api → :8000
│   └── package.json
│
├── docs/
│   ├── README.md                       this pack's index
│   ├── 01_PRD.md                       product requirements, as built
│   ├── 02_ARCHITECTURE.md              system architecture and ADRs
│   ├── 03_AI_AGENT_SPEC.md             orchestration and the model's contract
│   ├── 04_SECURITY_GROUNDING.md        threat model, grounding policy, limitations
│   ├── 05_IMPLEMENTATION_PLAN.md       the delivered Phase 1–15 record
│   ├── 06_EVALUATION_PLAN.md           evaluation method and results
│   ├── 07_API_SPEC.md                  the API contract
│   ├── 08_REPO_STRUCTURE.md            this file
│   ├── 09_DECISIONS.md                 frozen decisions, Phases 1–15
│   ├── 10_PHASE_13_REPORT.md           cross-domain validation, named entities
│   └── 11_PROMPTWARS_ALIGNMENT.md      problem statement alignment matrix
│
├── PHASE_14_REPORT.md                  independent adversarial validation
├── PHASE_15_REPORT.md                  structural safety and release hardening
├── README.md
├── .env.example
└── .gitignore
```

## Where things are not

Noted because their absence is a decision, not an oversight:

- **No `pages/` directory in the frontend.** The journey is one screen.
- **No database, no migrations, no ORM.** Documents are ephemeral (ADR-005).
- **No `agents/prompts.py`.** Prompts live in `models/prompts.py`, beside the
  provider, because the prompt *is* the provider's contract with the model.
- **No tool definitions.** The model has no tool access, and the graph's safety
  argument depends on that.
- **No CI configuration, no frontend Dockerfile, no deployment manifest.**

## Dependency direction

```text
API
 ↓
Agents (graph + runner)
 ↓
Documents · Models · Verification
 ↓
Schemas

Frontend
 ↓
Backend API only
```

Two rules are asserted by tests rather than by convention:

1. **The verification layer imports no provider.** It takes a `Finding` and
   anything satisfying the `EvidenceSource` protocol, so Nemotron, another
   vendor or a hand-written fixture all feed the same logic.
2. **The frontend never calls the NVIDIA API.** All model traffic is proxied
   through the backend, and the API key stays server-side.
