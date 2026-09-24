# Phase 23 — Gemini + Nemotron + Supabase migration

**Date:** 2026-09-23 · **Branch:** `migration/gemini` · **Baseline:** `ae48a10` on `master`

Every figure in this report comes from a command run on 2026-09-23 against this
branch. Nothing here was run against a live Gemini, NVIDIA, Supabase, Vercel or
Render account.

---

## A. Repository audit (before any change)

**Baseline, measured before editing:** backend 1603 passed, 1 skipped, 6
deselected (live). Frontend `tsc -b` clean, `oxlint` clean, `vite build` OK.
Playwright 34 passed. The repository had **no commits**, so the tree was
committed as-is as `ae48a10`, excluding `.env`, PDFs, the venv and `dist`.

**Architecture found:**
- a fixed LangGraph graph: `validate → ingest → coverage_gate → document_map → model → verify → output_gate`
- one provider, Nemotron, used for both analysis and Q&A through `ModelProvider`
- verification in `grounding.py`, `findings.py`, `semantics.py`, `qa.py` and `policy.py`
- a single release boundary (`release_findings` / `gate_answer`)
- everything in memory (ADR-005)

**Safety-critical components** (all left unchanged in behaviour):
- the coverage gate and its graph edge
- the verifier and its semantic axes
- `release_findings` / `explanation_decision`
- `gate_answer`
- injection refusal
- `redact()`
- the Phase 22 off-loop client construction under one deadline
- the JSON body cap
- the duplicate-analysis lock

**Risks found during the audit:**

| # | Risk | Outcome |
|---|---|---|
| R1 | Pydantic's `ValidationError` printed a **truncated NVIDIA key** in `input_value` whenever settings validation failed. | **Fixed:** `hide_input_in_errors=True`. Regression test `test_a_validation_error_never_echoes_a_key`. |
| R2 | The English-only semantic checks cannot judge a Tamil claim, explanation or answer. A Tamil model output would have passed through checks that could not read it. | **Designed out:** checked text stays in the document's language, and a translation is only an addition (§B.5). |
| R3 | With Gemini as the default, the test suite's key-blanking fixture (NVIDIA only) could let a developer's Gemini key turn a unit test into a live call. | **Fixed:** `conftest.py` blanks `GEMINI_API_KEY` and pins the roles for the legacy suite. |
| R4 | A reasoning call made late in an analysis could exceed the whole-run timeout and discard findings that had already been released. | **Fixed:** the run carries a deadline; reasoning is skipped below 10 s remaining and otherwise capped by the time left. Tested. |

---

## B. Changes implemented

### B.1 Provider roles (canonical configuration)
- `ANALYSIS_PROVIDER`, `QA_PROVIDER` (`gemini` | `nemotron`), `REASONING_PROVIDER` (`nemotron` | `none`) and the `REASONING_ENABLED` master switch.
- Reasoning is effective only when enabled **and** the provider is not `none`.
- An unknown value refuses to start. So does a Gemini role with no `GEMINI_MODEL`: the code never guesses a model name.
- Factories: `get_analysis_provider` (alias `get_model_provider`), `get_qa_provider` and `get_reasoning_provider`.
- **No fallback.** A Gemini role without a key fails with `provider_not_configured` even when an NVIDIA key is present. This is tested at the unit level and end to end.

### B.2 Shared transport vocabulary (`models/transport.py`)
- `ProviderFailureKind`, with exactly ten values: configuration, auth, rate_limit, capacity, network, timeout, construction_timeout, invalid_response, schema_invalid, unknown.
- It is derived from the existing Phase 19 `reason` strings, which are unchanged because tests assert them.
- The public `ErrorCategory` is **unchanged**.
- Nemotron's classification is byte-compatible; all existing provider tests pass unmodified.
- One addition: a timeout that fires before the client is built now records `construction_timeout`.

### B.3 Gemini (`models/gemini.py`)
- Uses the official `google-genai==2.25.0` (pin approved).
- Checked before writing: constructing `genai.Client` makes **no network call**, tested with sockets blocked. Retries default to one attempt, and are pinned to one anyway.
- The client is still built off the event loop, under the call's deadline (the Phase 22 pattern).
- Uses JSON mime type. The schema is enforced by the application's existing `parse_analysis` / `parse_answer`, not delegated to Google.
- Errors are classified from the SDK's own `APIError.code/.status` after key redaction.

### B.4 Nemotron reasoning stage (`models/reasoning.py`, `agents/nodes.py`, `agents/graph.py`)
- `NODE_SEQUENCE`, the release workflow, is **unchanged**. A separate `REASONING_SEQUENCE = [reason, reason_gate]` is reachable only from a successful `output_gate`.
- **Input:** released findings only (id, type, claim, quote, page). There is no page text, no withheld proposal and no `model_analysis`. This is asserted by test.
- **Output:** notes (category enum, text of at most 600 characters, 1–5 finding ids, 0–3 quotes, at most 20 notes).
- `reason_gate` withholds a note that:
  - cites an unknown id,
  - quotes anything that is not a substring of a cited finding's quote,
  - is instruction-like,
  - asserts a legal conclusion or verification (a closed regex list), or
  - states a figure its cited quotes lack.
- Released notes carry the fixed label **"Reasoning note — not independently verified"** and `evidence_checked` (the quotes are real). There is **no verification status**.
- Findings are deep-equal with and without reasoning, including under hostile notes (tested).
- A reasoning failure sets `reasoning.status` to one of failed, unavailable, skipped or disabled. The analysis stays `completed` with its findings unchanged (tested for 7 failure kinds).

### B.5 Multilingual (English, Tamil)

| Capability | Status |
|---|---|
| English analysis and Q&A | **Implemented**, unchanged |
| Tamil explanation / answer **translation**, labelled "not independently checked", released only beside a fully verified explanation or a fully supported answer, and only when every numeral in it appears in the evidence | **Partially implemented**. The translation is not semantically checked; numerals only. |
| Tamil / mixed documents: verbatim quote matching and wrong-figure rejection | **Partially implemented**. Tested on in-memory Tamil text at the verifier boundary; PyMuPDF's default font cannot render Tamil into a test PDF. |
| Deterministic document-language detection (`documents/language.py`, Tamil Unicode-block share) | **Implemented**. Used for persistence metadata, not for release. |
| Tamil polarity, modality and role semantics | **Deferred**. The semantic axes are English vocabularies. |
| Numbers written as Tamil words in a translation | **Not detected**. Limitation. |
| Other languages | **Explicitly excluded** |

This is stricter than the approved plan, which said to release a Tamil
explanation with `explanation_verified=false`. The checked explanation stays in
the document's language, and the translation is an additional labelled field,
so none of the existing checks is bypassed.

### B.6 Provenance
`result.provenance` and `answer.provenance` record `provider`, `model`,
`reasoning_provider` and `reasoning_model` (null when reasoning did not run, and
always null on answers), plus `verification_policy_version` and `status`. They
never include prompts, keys or model text.

### B.7 Supabase (optional, metadata only)
- **Migration:** 4 tables. RLS is enabled on every table and **no policy is created**. `REVOKE ALL` from anon/authenticated. `released_findings` has `CHECK (verification_status = 'verified')`. `ON DELETE CASCADE` from `documents`. A `lexguard_schema_version()` probe is executable by service_role only.
- **Repository:** `SupabaseRepository` uses `httpx`/PostgREST with no new dependency. Writes go to a 2-thread pool with a 5 s timeout and never block or fail a request.
- **Schema gate:** if the probe is missing or reports the wrong version, the repository disables itself.
- **Never stored:** PDFs, page text, the raw filename (salted SHA-256 plus extension only), questions, answers, withheld output, reasoning-note text.
- **Deletion:** delete-on-discard, TTL expiry, and a retention purge (`expires_at < now`) at startup and hourly.
- **Default:** `NullRepository`, which stores nothing, exactly as before.

### B.8 Frontend
- Types and services gain optional fields, and `VITE_API_BASE_URL`.
- A provenance strip reads: *"Analysis: Gemini · Reasoning notes: Nemotron · Verification: application-controlled"*. There is no "AI verified" wording anywhere, and a browser test asserts this.
- A reasoning notes panel shows the backend's label, an amber interpretation border, no verification badge, finding links that are keyboard operable, and states for each status.
- Language selectors for analysis ("Explanation language") and for Ask ("Answer language"). English sends exactly what was sent before; for analysis that means no body at all, and a test asserts it.
- Translations are rendered as text, labelled, with `lang="ta"`.
- `attention` is still not rendered. No Stitch metric was added.

### B.9 Deployment preparation
- `frontend/vercel.json`, with the bundle secret scan in the build command.
- `frontend/scripts/check-bundle.mjs`, tested in both directions.
- `render.yaml`: one Docker instance, secrets declared with `sync: false`.
- The Dockerfile honours `$PORT` and runs one worker.
- `/api/v1/ready` endpoint.
- `docs/12_DEPLOYMENT.md`.

---

## C. Files changed

**New (backend):**

| File | Purpose |
|---|---|
| `app/models/gemini.py` | Gemini provider |
| `app/models/reasoning.py` | Reasoning contract, prompt and schema |
| `app/models/transport.py` | Failure kinds, shared diagnosis, metadata logging |
| `app/documents/language.py` | Language detection |
| `app/schemas/provenance.py` | Provenance schema |
| `app/persistence/__init__.py` | Repository protocol, Null default, `persist_document` |
| `app/persistence/supabase.py` | PostgREST repository |
| `supabase/migrations/0001_lexguard_metadata.sql` | Metadata schema with RLS |
| `render.yaml` | Render blueprint |
| `tests/test_phase23_{config,gemini,reasoning,multilingual,persistence,deployment}.py` | 144 tests |
| `tests/test_reasoning_helpers.py` | Shared graph runner |

**Modified (backend):**

| File | Change |
|---|---|
| `core/config.py` | Roles, validators, readiness, secrets `repr=False`, `hide_input_in_errors` |
| `core/errors.py` | `ANALYSIS_IN_PROGRESS` |
| `models/{__init__,nemotron,prompts,provider}.py` | Factories; Nemotron reasoning and shared diagnosis; additive language directive (English prompt byte-identical); request language |
| `schemas/{findings,analysis,qa}.py` | Additive optional fields |
| `verification/policy.py` | `translation_decision`, `VERIFICATION_POLICY_VERSION`, language pass-through. **Release rules otherwise unchanged.** |
| `verification/qa.py` | Answer translation gate |
| `agents/{graph,nodes,state,runner}.py` | Reasoning appendix, provenance, per-job language with 409 on a cross-language race, deadline, failure kind, persistence hook |
| `api/v1/routes_{analysis,documents,health,qa}.py` | Optional analyze body, delete-on-discard, `/ready`, Q&A language and provenance |
| `documents/storage.py` | TTL expiry reaches persistence |
| `main.py` | Role logging, off-loop repository build, retention purge |
| `requirements.txt` | `google-genai==2.25.0` |
| `Dockerfile` | `$PORT`, one worker |
| `tests/conftest.py` | Pin legacy roles, blank all keys |
| `tests/test_document_overview.py` | Exact key set **extended** by the three approved fields; still an exact-match assertion |

**Frontend:**

| File | Change |
|---|---|
| `types/api.ts`, `services/api.ts`, `hooks/useAsk.ts`, `hooks/useAnalysis.ts` | Additive types, `VITE_API_BASE_URL`, language parameters |
| `components/findings/{ProvenanceStrip,ReasoningNotes}.tsx` (new) | Provenance strip, reasoning panel |
| `components/ui/LanguageSelect.tsx` (new) | Language selector, translation label |
| `FindingCard`, `FindingsView`, `AnswerCard`, `AskDocumentView`, `DocumentProcess`, `OverviewView`, `DocumentWorkspace` | Wiring |
| `e2e/specs/phase23.spec.ts` (new) | 12 flows |
| `e2e/stub_backend.py`, `e2e/make_fixtures.py` | Four scenarios |
| `vercel.json`, `.env.example`, `scripts/check-bundle.mjs`, `package.json` | Deployment |

**Root:** `.env.example` (canonical, every `Settings` field, enforced by test).

**Docs:** this report, `12_DEPLOYMENT.md`, and updates to `README.md`, `02`, `03`, `04`, `07`, `09` and `11`.

---

## D. Database
- Migration: `supabase/migrations/0001_lexguard_metadata.sql`.
- Tables: `documents`, `analysis_jobs`, `released_findings`, `qa_events`.
- RLS: enabled on all four, with zero policies. Browser roles are revoked. Only the service role (backend) writes.
- Retention: `SUPABASE_RETENTION_DAYS`, default 30, is set at first insert and cannot be extended by later writes.
- Deletion: `DELETE /documents/{id}` and TTL expiry delete the row, and the cascade removes everything linked.
- **Not anonymous:** rows are linked by document id, and a salted filename hash identifies a file to anyone holding both the file and the salt.
- **Local testing:** repository tests use `httpx.MockTransport`, and the migration is checked statically. **The migration has not been applied to any database.** Applying it to a Supabase branch or local stack needs your approval (G5).

---

## E. Testing (exact results, 2026-09-23)

```text
Backend tests:          1747 passed, 1 skipped, 6 deselected (live)   [baseline 1603 passed]
  of which Phase 23:    144 (config 21, gemini 30, reasoning 35, multilingual 26,
                             persistence 22, deployment 10)
Frontend type check:    tsc -b  exit 0
Frontend lint:          oxlint  exit 0
Frontend build:         vite build exit 0; bundle secret scan: no matches
                        (a planted fake key was detected: exit 1)
Browser tests:          46 passed   [baseline 34; +12 Phase 23]
Security tests:         included above (secret echo, redaction, no-fallback,
                        bypass for Gemini analysis and Q&A, reasoning isolation,
                        persistence privacy, bundle scan)
Database tests:         22 passed, mock transport + static SQL; NOT run on a live DB
Gemini stub tests:      30 passed
Nemotron stub tests:    existing provider/timeout suites unchanged + reasoning stub tests
Live provider tests:    NOT RUN (no approval requested for metered calls)
```

**Test edits to pre-existing files:**
- `conftest.py` pins the environment for the legacy suite.
- `test_document_overview.py` extends one exact key set.

No assertion was deleted or loosened.

---

## F. Security assessment
- **Secrets:**
  - The tree was scanned before the baseline commit. The only real key is in `.env`, which is gitignored.
  - Test hits are canaries.
  - Validation errors no longer echo keys (R1, fixed).
  - Keys are `repr=False`.
  - The bundle scan is part of the Vercel build.
- **Prompt injection:**
  - The existing defences are unchanged.
  - Reasoning input is fenced as untrusted, and notes are refused if instruction-like.
  - Translations are refused if instruction-like.
- **Verification:**
  - All Gemini output passes the unchanged verifier and gate. Five adversarial classes are withheld end to end: fabricated quote, polarity flip, wrong figure, role reversal, invented page.
  - Nemotron cannot mutate, create or verify findings.
- **Supabase:** backend-only, RLS with zero policies, schema probe gate, gated input types only.
- **Remaining limitations:**
  - No authentication, and therefore no per-user isolation.
  - The reasoning-note gate checks quotes and figures, not the note's reasoning.
  - Translations are checked for numerals only.
  - The Tamil injection check relies on the English detector.

## G. Deployment readiness
- **Vercel:** the configuration is ready and the build and bundle scan pass. Not deployed.
- **Render:** the blueprint is ready. Not deployed. Upload and body limits and the request timeout need checking against a real service.
- **Environment:** see `docs/12_DEPLOYMENT.md` §2.
- **CORS:** the exact Vercel origin, tested.
- **Supabase:** apply the migration and set three variables on Render. Optional.
- **Blockers:** see `docs/12_DEPLOYMENT.md` §8.

## H. Remaining work
1. **Before a local demo:**
   - Add `GEMINI_API_KEY` and `GEMINI_MODEL` to your `.env`. The backend refuses to start with a Gemini role and no model, which is by design.
   - **Rotate the NVIDIA key and any Google or Stitch key** that has appeared in chat or logs.
2. **Before hackathon submission:**
   - One approved live Gemini run through analysis and Q&A.
   - One approved live Nemotron reasoning run.
   - A demo PDF (none is committed).
3. **Before public deployment:**
   - Authentication and ownership.
   - An external job queue and state, to allow more than one instance.
   - Verification of host limits.
   - A live RLS check on a Supabase branch.
4. **Optional:**
   - A Tamil semantic vocabulary.
   - Detection of Tamil number words.
   - A progress stage for reasoning (it currently reports under `gating_output`).

## I. Recommendation
The migration is **functionally complete against stubs**, and every
safety-critical guarantee is intact, as measured by the full unchanged
pre-existing suite plus 144 new tests.

It is **not verified against live providers**. Gemini's real output quality on
these documents, and therefore how many findings survive verification, is
unknown until an approved live run. Nothing here establishes legal accuracy or
production readiness.

Recommended next step: an approved, isolated live run on a synthetic contract
before any demo claim.
