# Phase 22 — Provider Timeout & Cancellation Reliability Hardening

Date: 2026-09-23. Scope: Step 1 of the approved plan. Step 2 (socket timeout
via a private library attribute) is **deferred**, pending a separate
compatibility and cleanup assessment.

## 1. Executive summary

A live analysis on 2026-09-22 "never returned (18.7 minutes, no provider log
line)", despite a 180 s provider timeout and a 900 s workflow budget.

Controlled reproduction found that the model call itself was **not** the
problem: `ChatNVIDIA.ainvoke` already runs its blocking HTTP call in an
executor thread, and the 180 s timeout fired correctly around it. The defect
was one step earlier. Building the `ChatNVIDIA` client performs a synchronous
`GET /v1/models` with no socket timeout, and that build ran **on the event
loop, before any timeout was armed**. A stalled listing froze the entire
server: neither timeout could fire, `/health` stopped answering, and no
provider log line was written.

The fix moves client construction into a worker thread and places
construction and the model call under a single provider deadline. It changes
one method in one file. After the fix, the same stall ends as a
`provider_timeout` at the provider deadline while the server keeps answering.

No safety-critical module was modified. Timed-out runs publish no findings,
before or after the fix.

## 2. Investigation method

- Read the call path end to end, including the installed library source
  (`langchain-nvidia-ai-endpoints` 0.3.7, `langchain-core` 0.3.29,
  `langgraph` 0.2.61 in `backend/.venv`).
- Built a scratch reproduction harness (not committed) with a local fake of
  the hosted NVIDIA API. Each endpoint can reply normally, hang, return
  HTTP 500 or return malformed content. Every hang had a hard ceiling. A
  redirect at the `requests` adapter sent hosted-NVIDIA traffic to the fake
  and **refused every other host**, so no request reached NVIDIA.
- Ran three levels of reproduction:
  - **Provider level:** the real `NemotronProvider` and the real
    `ChatNVIDIA`.
  - **Server level:** the real uvicorn/FastAPI/LangGraph app in a separate
    process, with `/health` probed every 250 ms (1 s client timeout) to
    detect a frozen event loop.
  - **Shutdown:** `asyncio.run` exit time after a timeout.
- Timeouts were scaled down to 1–3 s (provider), 6 s (workflow) and 2 s
  (Q&A).

## 3. Actual call path

```text
POST /api/v1/documents/{id}/analyze → runner.submit → asyncio.create_task(_run)
 └ runner._run: asyncio.wait_for(_execute, ANALYSIS_TIMEOUT_SECONDS=900)
   └ LangGraph astream (sync nodes run in executor threads)
     └ analyze_node → provider.analyze_document → NemotronProvider._invoke
         BEFORE: client = self.client   ← ChatNVIDIA(...) on the loop; GET /v1/models, no timeout
                 wait_for(client.ainvoke(...), MODEL_TIMEOUT_SECONDS=180)
         AFTER:  async with asyncio.timeout(MODEL_TIMEOUT_SECONDS):
                     client = await asyncio.to_thread(build)      (first use only)
                     response = await client.ainvoke(...)
           └ BaseChatModel._agenerate → loop.run_in_executor(None, _generate)
             └ requests.Session.post(...)   timeout=None (observed at the adapter)
```

`/ask` reaches the same `_invoke` method under an additional
`wait_for(QA_TIMEOUT_SECONDS=120)`. `get_model_provider()` creates a new
provider per request, so before the fix the listing GET ran on the event
loop for **every** analysis and every question.

## 4. Root cause and confidence

**Confirmed by controlled test:**

- The client build blocks the event loop and escapes both timeouts:
  - provider level (S3b): 8.05 s loop stall;
  - server level (E3): the 6 s workflow budget was ignored, the run ended
    only when the fake upstream dropped the connection at 20.3 s, and 14 of
    15 health probes failed;
  - both cases wrote no provider log line.
- A build failure escaped as a raw `ConnectionError` rather than a
  classified `ModelError`.
- The configured model is absent from ChatNVIDIA's static table, which is
  what triggers the listing request.
- `requests` receives `timeout=None`.

**Strong hypothesis:** the 2026-09-22 incident was this failure. It is the
only provider step that can hang without writing a provider log line, and
the reproduction matches that signature. No server log of the incident
exists, so this cannot be confirmed.

**Unresolved:**

- What ended the incident at 18.7 min. The frontend's poll ceiling
  (`MAX_POLL_MS`) is 20 min.
- Which NVIDIA endpoint stalled.

## 5. Before / after behaviour

Timings are from the scratch harness (fake upstream, scaled-down timeouts).

| Scenario | Before | After |
|---|---|---|
| Analysis, model call hangs (E1) | `provider_timeout` 4.3 s, health 12/12 | `provider_timeout` 3.2 s, health 9/9 |
| **Analysis, listing GET hangs (E3)** | **ran 20.3 s (budget 6 s), health 1 ok / 14 failed, reported `analysis_timeout`, no provider log** | **`provider_timeout` 3.2 s, health 8/8, provider log `outcome=timeout`** |
| `/ask`, model call hangs (E5) | 504 in 2.07 s | 504 in 2.07 s |
| **`/ask`, listing GET hangs (E6)** | **503 after 20.0 s, health 0 ok / 15 failed** | **504 `model_timeout` in 2.02 s, health 4/4** |
| Resubmit after timeout (E2/E4), `/ask` after hangs (E7) | succeeds | succeeds |
| Two concurrent hanging analyses (E8) | both `provider_timeout` | both `provider_timeout` |
| `/findings` after any timeout | 409 | 409 |

Provider-level results before the fix:

| Scenario | Result |
|---|---|
| S1 success | ok |
| S2 async sleep | `ModelTimeoutError` 2.01 s, loop responsive |
| S3a model call hangs | `ModelTimeoutError` 2.02 s, loop responsive, upstream connection left open |
| S3c `time.sleep` inside `ainvoke` | loop blocked 5 s; the timeout cannot fire. Inherent to any blocking code on the loop, and not present in the real client. |
| S4 HTTP 500 | `ModelUnavailableError` (`upstream_server_error`) |
| S5 cancellation | `CancelledError` propagates; the thread and socket are left behind |
| S6 malformed reply | `ModelResponseError` (`no_json_object`) |
| S7 success after timeout | ok |

## 6. Files changed

| File | Change |
|---|---|
| `backend/app/models/nemotron.py` | `_invoke` now checks the key first (unchanged `ModelNotConfiguredError` semantics), then runs construction and the call under one `asyncio.timeout(model_timeout_seconds)`. New `_resolve_client()` builds the client via `asyncio.to_thread` and stores it only after the await returns, in the coroutine, so an abandoned build is never stored. Construction failures now pass through the existing `_diagnose`/`_log` handling. |
| `backend/tests/test_provider_timeout_phase22.py` | New, 16 tests. |
| `docs/PHASE_22_REPORT.md` | This report. |

## 7. Tests added

Every stall waits on a `threading.Event` with a 5 s ceiling, and timeouts are
1 s, so no test can hang. No test makes network calls.

| Test | Covers |
|---|---|
| `test_a_stalled_construction_times_out_without_blocking_the_loop` | timeout < 2 s; loop stall < 0.5 s; build ran off the main thread |
| `test_a_construction_that_finishes_late_publishes_nothing` | the late build is not stored or called; the next request rebuilds and succeeds |
| `test_a_construction_network_failure_is_classified_and_logged` | `ModelUnavailableError` with reason `network_failure`, plus a provider log line |
| `test_a_stalled_construction_is_logged_as_a_timeout` | `outcome=timeout` is logged |
| `test_missing_key_is_still_not_configured_and_starts_no_thread` | configuration errors stay classified as configuration errors |
| `test_the_client_is_built_once_per_provider` | a provider builds its client once |
| `test_a_blocking_model_call_times_out_with_a_responsive_loop` | guards the already-correct model-call path |
| `test_construction_and_call_share_one_deadline` | build and call share one budget |
| `test_cancellation_propagates` | cancellation is not swallowed |
| `test_success_after_a_timeout` | recovery after a timeout |
| **`test_the_abandoned_constructor_cannot_publish_and_the_app_stays_responsive`** | the approval addition: the build completes after the timeout; the job stays `failed/provider_timeout` with `verified_count` null; `/findings` returns 409; `/health` answers in < 1 s; the built client is never called; a resubmission completes |
| `test_a_stalled_construction_is_a_provider_timeout_and_the_server_answers` | API level |
| `test_a_model_call_that_completes_late_is_discarded` | a late model result never reaches the job |
| `test_concurrent_stalled_analyses_both_fail_cleanly_and_can_rerun` | concurrent hangs |
| `test_timeout_logs_carry_no_key_and_no_document_text` | log safety |
| `test_a_stalled_construction_is_a_504_within_the_question_budget` | `/ask` |

**Mutation check.** With the pre-fix `_invoke` temporarily restored, 10 of
the 16 tests failed and 6 passed. The 6 that passed are guards for paths that
were already correct. One caveat: `test_missing_key_is_still_not_configured…`
fails against the old code only because its stub builder bypasses the old
key check. It is not evidence of the defect.

## 8. Full test results

All runs used `backend/.venv` (Python 3.11.9).

| Suite | Before | After |
|---|---|---|
| Backend `pytest` | 1587 passed, 1 skipped, 6 deselected (104.8 s) | **1603 passed, 1 skipped, 6 deselected (195.9 s)** |
| New tests alone | — | 16 passed (17.0 s) |
| Frontend `tsc -b` | — | exit 0 |
| `oxlint` | — | exit 0 |
| `vite build` | — | succeeded |
| Browser (Playwright, stub backend) | — | **27 passed (2.8 min)** |

The 6 deselected backend tests are the `live` tests; they were not run.

## 9. Timeout and cancellation behaviour (after)

- Any stall in the provider — building the client or calling it — ends as
  `ModelTimeoutError` → `provider_timeout` within `MODEL_TIMEOUT_SECONDS`,
  with a provider log line.
- The workflow budget (900 s) and the Q&A budget (120 s) are enforceable
  again, because the event loop is never blocked by the provider.
- Cancellation propagates through LangGraph to the runner, which records a
  terminal failure.
- An error raised by the library itself as `TimeoutError` is still reported
  as a timeout, as before.

## 10. Resource cleanup behaviour

**Not solved by Step 1, and stated plainly.** A timed-out build or model call
leaves its worker thread blocked in `requests` until the upstream closes the
socket, because `requests` is given no socket timeout.

Observed consequences of such a thread:

- It holds one default-executor slot: `min(32, cpu + 4)`, which is 20 on the
  test machine.
- Enough simultaneously stuck threads make even healthy calls time out.
  This was demonstrated at a reduced pool size of 2.
- It delays clean interpreter shutdown: `asyncio.run` waited 10.06 s in the
  reproduction, and in production the wait has no upper bound.

This is the purpose of the deferred Step 2.

## 11. Security and safety impact

- **Unchanged:** evidence verification, semantic verification,
  `release_findings`, output gates, prompts, citation validation,
  neutralisation of model-controlled fields, Q&A grounding and the safe error
  vocabulary.
- **Not added:** retries, fallback, model substitution or new background work.
- **Error classification:** a construction failure is now classified by the
  existing `_diagnose` logic. Before, it surfaced as a raw exception that the
  node mapped to `internal_error`. Log lines remain metadata only, and a test
  asserts that neither the key nor document text appears in them.
- **Publishing:** a timed-out run cannot publish. `build_result` is reached
  only after the output gate, and abandoned results have no owner.

## 12. Known limitations

- Abandoned threads and sockets remain until the upstream closes them
  (section 10). Step 2 is deferred.
- The model-listing request inside the `ChatNVIDIA` constructor would stay
  without a socket timeout even under the Step 2 design.
- An abandoned request may still complete, and be billed, on NVIDIA's side
  while the user's resubmission runs.
- A provider object is still created per request, so the listing GET still
  runs on every request. It now runs off the event loop and inside the
  provider deadline.
- Only the stall mode was reproduced. The real upstream's behaviour during
  the incident is unknown.

## 13. Live validation status

**Not performed.** No call was made to NVIDIA in this phase. Real-backend
validation used the real server stack against a local fake upstream. Nothing
here measures, or supports any claim about, live NVIDIA reliability.

## 14. Git diff summary

The repository has no commits (`master` has no history), so no `git diff` is
available. Everything is untracked. Relative to the state at the start of the
phase:

- `backend/app/models/nemotron.py`: one method rewritten, one method added
  (about 25 lines).
- `backend/tests/test_provider_timeout_phase22.py`: new, 473 lines.
- `docs/PHASE_22_REPORT.md`: new.

## 15. Recommendation for the next phase

1. **Assess Step 2 separately.** Compare three ways of bounding abandoned
   threads:
   - a session factory with a socket timeout, set via the private
     `_client.get_session_fn`;
   - a dedicated, bounded executor for provider calls;
   - a thin HTTP client that the application owns.

   Criteria: compatibility across library versions, cleanup on shutdown, and
   keeping the application deadline firing before the socket deadline.
2. **Consider building one client per process** to remove the per-request
   listing request. This changes lifecycle behaviour (for example, rotating
   the API key would need a restart), so it needs its own evaluation.
3. **Update the timeout wording** in `docs/03_AI_AGENT_SPEC.md` and the
   README limitations section to record this defect and fix.
