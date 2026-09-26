# LexGuard AI — Final Deployment Readiness Report

**Branch:** `migration/gemini`  
**Timestamp:** 2026-09-26

---

## Frontend — Vercel

| Item | Status | Detail |
|---|---|---|
| Vercel ready | **YES** | `frontend/vercel.json` present with framework, build command, SPA rewrites, security headers |
| Build command | `npm run build && npm run check:bundle` | Runs `tsc -b && vite build` then bundle-size assertion |
| Output directory | `dist` | Confirmed by `vercel.json` |
| Framework detection | `vite` | Declared in `vercel.json` |
| SPA routing | YES | `rewrites: [{ source: "/(.*)", destination: "/index.html" }]` |
| Security headers | YES | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` |
| Environment variables | `VITE_API_BASE_URL` | Set in Vercel Project Settings → Environment Variables. Leave empty in dev (Vite proxy). |
| Production API URL | `https://<render-service-name>.onrender.com` | Set as `VITE_API_BASE_URL` in Vercel |
| Localhost references | None | No hardcoded localhost URLs in source |
| Secret leakage | None | Only `VITE_*` variables reach the browser; no API keys |
| Production build verified | YES | 307 KB JS (90 KB gzip), 35 KB CSS (7 KB gzip), clean output |

### Vercel Setup Steps

1. Import the repository in Vercel.
2. Set root directory to `frontend`.
3. Vercel auto-detects Vite. Build command and output directory are set via `vercel.json`.
4. Add environment variable: `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`
5. Deploy.

---

## Backend — Render

| Item | Status | Detail |
|---|---|---|
| Render ready | **YES** | `render.yaml` present with Docker runtime, health check, environment variables |
| Runtime | Docker | `backend/Dockerfile` present |
| Root directory | `backend` | `rootDir: backend` in render.yaml |
| Start command | uvicorn via Dockerfile | PORT injected by Render at runtime |
| Health endpoint | `GET /api/v1/health` | Returns `{"status": "ok"}` |
| `numInstances` | 1 | In-process job runner requires single instance |
| CORS | `ALLOWED_ORIGINS` env var | Set to the exact Vercel origin in Render dashboard |
| Required env vars (set in Render dashboard) | `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `ALLOWED_ORIGINS`, `GEMINI_MODEL` | See `.env.example` for full list |
| Optional env vars | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PERSISTENCE_HASH_SALT` | Omit for in-memory mode |

### Render Environment Variables (Required)

```
APP_ENV=production
ANALYSIS_PROVIDER=gemini
QA_PROVIDER=gemini
REASONING_PROVIDER=nemotron
REASONING_ENABLED=true
GEMINI_MODEL=gemini-3.8-flash
NEMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b
ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app   # set sync:false in dashboard
GEMINI_API_KEY=<your-key>                               # set sync:false in dashboard
NVIDIA_API_KEY=<your-key>                               # set sync:false in dashboard
```

### Render Setup Steps

1. Create a new Web Service in Render, connect the repository.
2. Select the `render.yaml` blueprint, or configure manually: root `backend`, Docker runtime.
3. Set the `sync: false` secrets in the Render dashboard: `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `ALLOWED_ORIGINS`.
4. Deploy.

---

## Integration — Vercel → Render

| Item | Status | Detail |
|---|---|---|
| HTTPS | YES | Both Vercel and Render provide TLS by default |
| API connectivity | `VITE_API_BASE_URL` → Render URL | Set in Vercel env vars |
| CORS | `ALLOWED_ORIGINS` → Vercel URL | Set in Render dashboard |
| No localhost references | YES | Verified |
| No secrets in frontend | YES | Verified |
| Provider keys backend-only | YES | `GEMINI_API_KEY` and `NVIDIA_API_KEY` never in frontend bundle |

---

## What Has NOT Been Verified Live

- End-to-end analysis on the deployed Render URL (Gemini quota blocked Phase 24 live gate)
- Vercel → Render round-trip in production (configuration is correct; not tested live)
- Supabase persistence (intentionally optional; not configured in demo)
