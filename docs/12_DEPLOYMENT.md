# 12 — Deployment and configuration (Phase 23)

**Status: prepared, not deployed.** Nothing in this document has been run
against a live Vercel, Render or Supabase account. The configuration files
exist and are checked by tests (`backend/tests/test_phase23_deployment.py`),
and the frontend build and bundle scan pass locally. That is all this document
claims.

---

## 1. Topology

```text
Browser ──HTTPS──> Vercel (static React/Vite build)
   │
   └──HTTPS──> Render web service (Docker: FastAPI, 1 instance)
                  ├── Gemini API        analysis + Q&A (default)
                  ├── NVIDIA API        reasoning notes (Nemotron)
                  └── Supabase (opt.)   metadata + released findings only,
                                        service-role key, server-side only
```

The browser talks **only** to the FastAPI backend. It never calls Gemini,
NVIDIA or Supabase, and holds no key for any of them.

### Why the backend is not on Vercel

| Constraint | Consequence |
|---|---|
| An analysis runs for minutes (per-call timeout 180 s, whole-run budget 900 s). | Needs a process that outlives a request. |
| Jobs are tracked by an in-process runner (`app/agents/runner.py`) and polled. | State must live in one long-running process. |
| Uploads sit in a temporary workspace until `DOCUMENT_TTL_SECONDS`. | Needs a filesystem that persists between requests. |
| Duplicate-analysis protection is an in-process lock. | Exactly one instance (`numInstances: 1`, `--workers 1`). |

A serverless function provides none of these. Moving the backend to Vercel
would need a job queue and external state first. That is a redesign and is not
planned here.

---

## 2. Provider configuration (canonical)

The single source of truth is `Settings` in `backend/app/core/config.py`.
`.env.example` documents every field, and a test fails if the two drift apart.

| Variable | Values | Default | Notes |
|---|---|---|---|
| `ANALYSIS_PROVIDER` | `gemini` \| `nemotron` | `gemini` | Unknown value: the app refuses to start. |
| `QA_PROVIDER` | `gemini` \| `nemotron` | `gemini` | Independent of analysis. |
| `REASONING_PROVIDER` | `nemotron` \| `none` | `nemotron` | |
| `REASONING_ENABLED` | bool | `true` | Master switch. Reasoning runs only if `true` **and** provider ≠ `none`. |
| `GEMINI_API_KEY` | secret | — | Required for any Gemini role to work. |
| `GEMINI_MODEL` | string | none in code | **Required** when any role is `gemini`, otherwise startup fails. `.env.example` sets `gemini-3.8-flash`, taken from Google's model list on 2026-09-23. |
| `NVIDIA_API_KEY` | secret | — | Required for Nemotron roles and reasoning. |
| `REASONING_TIMEOUT_SECONDS` | int | 90 | Also capped by the time remaining in `ANALYSIS_TIMEOUT_SECONDS`. |

**Startup rules**

- An unknown enum value is a startup error. Validation errors never echo input
  values (`hide_input_in_errors`), so no truncated key appears in logs.
- A missing key is **not** fatal. The startup log names the missing variable,
  and that role answers `503 model_not_configured` / `provider_not_configured`.
- With reasoning on but no NVIDIA key, analyses complete normally and
  `reasoning.status` is `unavailable` with `failure_kind: configuration`.
- **There is no fallback.** Each role calls only the provider named for it. A
  Gemini role with no Gemini key fails; it does not use Nemotron.
  `result.provenance` and `answer.provenance` record the provider actually
  called.

`GET /api/v1/ready` reports the selected providers, per-role booleans and
whether persistence is enabled. It never includes a key.

---

## 3. Frontend on Vercel

- Project root: `frontend/`. `vercel.json` sets the build to
  `npm run build && npm run check:bundle`, the output to `dist`, an SPA rewrite
  and three security headers.
- **The only environment variable** is `VITE_API_BASE_URL`, the Render
  service's `https://` origin with no trailing slash. It is public: Vite inlines
  it into the bundle.
- `npm run check:bundle` fails the build if `dist/` contains anything shaped
  like a Google, NVIDIA or Supabase secret, a JWT, or a server-side variable
  name. It was checked in both directions: a planted fake key fails the build,
  and the clean build passes.
- A test asserts that frontend source reads no `import.meta.env` value other
  than `VITE_API_BASE_URL` and names no server-side secret.

## 4. Backend on Render

- `render.yaml` (repo root) declares one Docker web service built from
  `backend/Dockerfile`, with `numInstances: 1` and health check
  `/api/v1/health`.
- The Dockerfile listens on `${PORT:-8000}` with one worker.
- Every secret is declared with `sync: false`, so Render prompts for it in its
  dashboard and no value is committed. A test enforces this.
- **CORS:** set `ALLOWED_ORIGINS` to the exact Vercel origin. A test confirms
  that the configured origin is allowed and any other origin receives no CORS
  header. Methods allowed: GET, POST, DELETE. Credentials are not used.
- **Uploads:** the backend caps uploads at `MAX_UPLOAD_BYTES` (25 MiB). If
  Render or a proxy in front of it has a lower request-body limit, that lower
  limit applies. Verify before a demo.
- **Timeouts:** the browser polls analysis status, so no single HTTP request
  lasts as long as the model call. `/ask` is synchronous and bounded by
  `QA_TIMEOUT_SECONDS` (120 s). Check that the host's request timeout is longer
  than that.
- **Free-tier sleep:** a sleeping instance loses all in-memory documents and
  jobs. This is expected with ADR-005. A reader sees "document not found" and
  uploads again.

## 5. Supabase (optional)

Off by default. With `SUPABASE_URL` unset, the app behaves exactly as before
Phase 23.

1. Create a project, or better, a **branch** for testing.
2. Apply `supabase/migrations/0001_lexguard_metadata.sql`, for example with
   `supabase db push` or the SQL editor. **Nothing in this repository applies
   it automatically, and no remote project was touched in Phase 23.**
3. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `PERSISTENCE_HASH_SALT`
   on Render only.
4. On startup the backend calls `lexguard_schema_version()`. If that call fails
   or returns an unexpected version, persistence disables itself and logs
   `persistence_disabled reason=schema_missing`. A project without the
   migration, and therefore without its RLS, is never written to.

What is stored, and what is not, is covered in
`docs/09_DECISIONS.md` (ADR-005 amendment).

**Limitation:** the app has no authentication, so rows carry no owner and
there is no per-user isolation. This is acceptable for a single-tenant demo and
is a blocker for any public multi-user deployment.

## 6. Secrets checklist

- [ ] `.env` is not committed (`.gitignore` covers `.env` and `.env.*`, and
      allows only `.env.example`).
- [ ] `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY` and
      `PERSISTENCE_HASH_SALT` are set only in Render.
- [ ] Vercel has only `VITE_API_BASE_URL`.
- [ ] `npm run check:bundle` passes.
- [ ] **Rotate** any key that has appeared in a chat, screenshot, log or
      terminal output. The NVIDIA key and any Google or Stitch key shown during
      development fall into this category.
- [ ] `APP_ENV=production` on Render. Persistence then also requires the salt.

## 7. Rollback

| Layer | Rollback |
|---|---|
| Frontend | Vercel → Deployments → promote the previous deployment. |
| Backend | Render → the service → Deploys → roll back to the previous deploy. |
| Code | `git revert <commit>`. The pre-migration baseline is commit `ae48a10` on `master`. |
| Providers | Set `ANALYSIS_PROVIDER=nemotron QA_PROVIDER=nemotron REASONING_ENABLED=false` to return to the pre-Phase-23 provider behaviour without a code change. |
| Persistence | Unset `SUPABASE_URL`. The app returns to in-memory only. Stored rows remain until they are deleted or reach retention. |

## 8. Known blockers before public deployment

1. No authentication, and therefore no per-user isolation. Anyone with a
   document id can use it within its TTL.
2. In-process state limits the backend to one instance.
3. The live Gemini path has not been exercised. The Phase 23 default suite uses
   stubs only.
4. Host body-size and timeout limits have not been verified against a real
   Render service.
