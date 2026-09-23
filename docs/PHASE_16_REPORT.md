# Phase 16 Report

## Controlled Demo Document + One Live End-to-End Validation

---

## 1. Executive summary

Phase 16 had two jobs: build a controlled document the demo can be rehearsed
on, and use it to close the one gap Phase 15 left open — the Phase 15 output
policy had never run against live model output through the shipped endpoints.

**Task 1 succeeded. Task 2 is BLOCKED, not failed.**

The demo contract exists, is reproducible, and its expected results were
**derived by running the shipped verifier** rather than assumed. The live run
reached the model node of the real workflow and was refused by the provider
after 1,045 ms with a capacity error — the same signature Phase 15 recorded.
Per this phase's own rule, no retry was made and no success is claimed.

One further thing was established that the Phase 16 readiness assessment had
only inferred: **the existing live test could not have closed this gap anyway.**
`test_nemotron_live_phase14.py::test_findings_survive_the_shipped_verification_path`
stops at `verify_analysis_claims` and never calls `policy.release_findings` or
the findings endpoint. The gap is a coverage gap first and a capacity problem
second.

**No verification logic, prompt, schema, endpoint, test or configuration was
modified in this phase.**

---

## 2. Task 1 — the demo contract

### Location and shape

| | |
|---|---|
| Generator (source of truth) | `demo/make_demo_contract.py` |
| Output | `demo/demo_services_agreement.pdf`, **3 pages** |
| Committed? | No — `.gitignore:17` (`*.pdf`) excludes it. **No `.gitignore` change was made.** |
| Convention followed | `frontend/e2e/make_fixtures.py` — generator committed, artefact generated |
| Recreate with | `backend/.venv/Scripts/python.exe demo/make_demo_contract.py` |

### Clauses

| Page | Clause | Checkable fact |
|---|---|---|
| 1 | Demonstration notice + parties | Fictional; marked on the page itself |
| 1 | 2. Term and Renewal | 1 April 2026, 12 months, auto-renewal **unless** 60 days notice |
| 2 | 3. Fees and Payment | `Rs 50,000` per month, 15-day payment window, 1.5% interest |
| 2 | 4. Termination | 30 days written notice; immediate for unremedied material breach (15 days) |
| 2 | 5. Expenses | Pre-approved travel only |
| 3 | 6. Confidentiality | **Prohibition** — must not disclose; survives 3 years |
| 3 | 7. Limitation of Liability | `Rs 6,00,000` aggregate cap |
| 3 | 8. Governing Law | Laws of India; courts at Chennai |
| 3 | 9. Notices + signature block | Placeholder signatories only |

Fictional throughout. No real party, person, address or confidential
information. Page 1 states that it is a demonstration document with no legal
effect, so the disclaimer travels with the file.

### Two drafting decisions, both measured

1. **`Rs`, not the rupee sign.** A probe confirmed PyMuPDF's base-14 Helvetica
   has no glyph for U+20B9: it extracts as a middle dot (`·50,000`), which
   would break value verification and misrepresent the document. `Rs` is in the
   verifier's currency vocabulary, renders, and round-trips. Confirmed by
   running the parser: `Rs 50,000` → `currency 50000`.
2. **ASCII only**, asserted by the generator, so a typographic apostrophe
   cannot differ between page and quote.

Neither is a workaround for a defect. Both are recorded here rather than left
for someone to rediscover.

---

## 3. Expected findings — derived, not assumed

Full table: `docs/PHASE_16_EXPECTED_FINDINGS.md`. Produced by running
`verify_analysis_claims` followed by `policy.release_findings` against the
generated PDF, with no model call.

| ID | Type | Expected result | Evidence | Page | Reason |
|---|---|---|---|---|---|
| P1 | termination | **released** | "…giving 30 days written notice" | 2 | Quote on page; duration matches |
| P2 | payment | **released** | "a fee of Rs 50,000 per month" | 2 | Currency matches its own evidence |
| P3 | confidentiality | **released** | "must not disclose Confidential Information…" | 3 | Prohibition preserved |
| P4 | renewal | **released** | "shall renew automatically for successive periods" | 1 | Condition carried |
| P5 | liability | **released** | "shall not exceed" | 3 | Cap matches; `attention` derived **high** |
| P6 | governing_law | **released** | "governed by the laws of India" | 3 | Verbatim |
| N1 | polarity reversal ("may disclose") | **withheld** | genuine prohibition | 3 | `claim_contradicted` |
| N2 | Rs 50,000 → Rs 75,000 | **withheld** | genuine fee clause | 2 | `currency_mismatch` |
| N3 | 30 days → 60 days | **withheld** | genuine termination clause | 2 | `numeric_mismatch` |
| N4 | fabricated citation on a true claim | **released, citation dropped** | genuine termination clause | 2 | Published `section` is `null` |
| N5 | renewal condition dropped | **withheld** | genuine renewal clause | 1 | `claim_unsupported` |
| N6 | cap asserted using a figure from another page | **withheld** | genuine liability clause | 3 | `currency_mismatch` |

**7 released, 5 withheld.**

N4 is the instructive case: the claim is true and only the citation is
invented, so the finding survives and the citation is removed — neither losing
true information nor lending false authority.

> **A correction to my own working note during this phase.** An intermediate
> script printed the *model-supplied* section rather than the *published* one
> and appeared to show a fabricated citation being released. It was not. The
> published field is `null`. The scripting error was mine; the application
> behaved as documented.

---

## 4. Task 2 — live validation

# LIVE VALIDATION BLOCKED

Not failed, and not succeeded. The application behaved correctly; the provider
did not serve the request.

| | |
|---|---|
| Model identifier | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` |
| Endpoint | `https://integrate.api.nvidia.com/v1` |
| Inference attempts | **1** (no retry, per this phase's rule and the system's design) |
| Model call latency before failure | **1,045 ms** |
| Analysis duration | **2,342 ms** |
| Analysis status | `failed` |
| Stage reached | `analyzing` — i.e. the model node of the real graph |
| Error category | `provider_unavailable` |
| User-facing message | "The analysis service is temporarily unavailable." |
| Findings count | n/a — the run did not reach verification |
| Released / withheld | n/a |
| Coverage (measured before the call) | `complete`, 3 of 3 pages, 0 failed, 0 unreadable, not repaired |
| Findings endpoint response | Correct refusal: `"The analysis for this document has not completed."` |

**Expected vs actual:** the expected-findings table could not be compared
against live output, because no model output was produced. That comparison
remains outstanding and is the sole objective of any follow-up attempt.

### Why this is capacity, not configuration

A failure at 1,045 ms is far too fast to be inference on three pages — the one
recorded successful analysis in this project took roughly 37 seconds for a
single page. The key was accepted (an invalid credential raises a distinct
`ModelAuthError`), the model identifier was accepted, the payload was built,
and the request reached the endpoint. This matches the
`503 ResourceExhausted: Worker local total request limit reached` pattern
recorded in Phase 15 §10.

### What this does and does not establish

**Exercised, live, through the real application:**

| Layer | Status |
|---|---|
| Upload + validation | ✅ 201, 3 pages, `source_repaired: false` |
| Extraction | ✅ Real PyMuPDF, per-page manifest |
| Coverage gate | ✅ `complete`, `analysis_eligible: true` — computed by the application |
| LangGraph workflow | ✅ Reached the model node through the real graph |
| Nemotron (hosted) | ❌ Refused — provider capacity |
| Phase 5 evidence verification | ⛔ Not reached |
| Phase 14 semantic verification | ⛔ Not reached |
| Phase 15 output policy | ⛔ **Not reached — the gap remains open** |
| Findings API | ✅ Reached, and correctly refused to publish |
| Failure handling | ✅ Typed category, safe message, no leak, no retry |
| Frontend | Not exercised in this run (API-driven) |

The failure path itself validated cleanly: a provider outage produced a typed
category, a safe user-facing message, a correct refusal from the findings
endpoint, and no partial or fabricated result. That is worth something, but it
is **not** the validation this phase set out to obtain.

---

## 5. The coverage gap behind the capacity problem

Recorded because it changes what a future attempt must do.

`test_nemotron_live_phase14.py::test_findings_survive_the_shipped_verification_path`
calls `verify_analysis_claims` and asserts on `is_displayable_as_fact`. It
never calls `policy.release_findings`, and it never goes through FastAPI. So
even on a day when the provider has capacity, `pytest -m live` would re-validate
the **Phase 14** seam and leave the Phase 15 boundary untouched.

Closing the gap therefore requires either a new live test that drives the real
endpoints — a test addition, which this phase was explicitly not authorised to
make — or a repeat of the manual run in §4, which needs no code change at all.

---

## 6. Security

| Check | Result |
|---|---|
| API key printed | **No.** Configuration was confirmed by asserting key *length* (70) |
| API key in this report | **No** |
| API key in source | **No** |
| `.env.example` modified | **No** |
| `.env` gitignored | **Yes** — `.gitignore:2` |
| Key in server logs | **No** — 0 occurrences of `nvapi` |
| Prompt in logs | **No** — 0 occurrences of the untrusted-content markers |
| Document text in logs | **No** — 0 occurrences of party names, clause text or `Rs 50,000` |
| Full model response logged | **No** — no model output was produced |
| Provider abstraction bypassed | **No** — the run went through the real `NemotronProvider` via the real endpoints |

Log lines recorded ids, page counts, outcome type and latency only, which is
what the specification requires.

---

## 7. Tests

Reported separately from the live attempt, as required.

### Offline (after Task 1)

```text
cd backend && .venv/Scripts/python.exe -m pytest -p no:cacheprovider
1437 passed, 1 skipped, 6 deselected, 6 warnings in 35.87s
```

Identical to the Phase 15 baseline. No test was added, modified, weakened or
deleted, and no permanent live test was introduced.

### Frontend

Not re-run in this phase; no frontend file was touched.

### Live

Reported in §4 only. **Not mixed into the offline figures.**

---

## 8. Problems discovered

Documented, not fixed, per this phase's rule.

| # | Problem | Severity | Where | Status |
|---|---|---|---|---|
| 1 | The Phase 15 output policy is still unvalidated against live model output | **High** (evidence gap, not a defect) | Provider capacity + §5 test coverage | ~~Open — needs one successful run~~ **Closed 2026-09-22**: two successful live runs, releasing 2 of 9 and 1 of 9 proposed findings. Repeatability remains unmeasured (2 of 6 attempts that day). See `docs/11_PROMPTWARS_ALIGNMENT.md` §6.2 |
| 2 | The existing live test cannot close gap 1 | Medium | `test_nemotron_live_phase14.py:123` | Open — adding a test is a separate decision |
| 3 | The rupee sign does not survive PDF generation with the base-14 font | Low (tooling, not application) | PyMuPDF/Helvetica | Worked around in the demo document and documented |
| 4 | `GET /analysis/{id}/status` contains two `status` fields — the analysis's and `coverage.status` — and a naive first-match parse reports `complete` while the analysis has failed | Low (client trap, not a backend defect) | Response shape | Documented in the runbook §4; **no schema change made** |

Nothing found in this phase indicates a defect in the verification logic. Items
1 and 2 are evidence gaps; 3 is a font limitation; 4 is a client-side hazard
that the API's own field names do not create but its nesting invites.

---

## 9. PromptWars alignment

The demo demonstrates the theme **AI for Legal Assistance & Access** as follows,
and claims nothing beyond it:

| PS idea | How the demo shows it |
|---|---|
| Legal documents are difficult to understand | A three-page agreement with a conditional renewal, a prohibition, a cap and a notice period — the structures non-lawyers misread |
| Users need help navigating legal information | Findings carry the clause type, a plain-language claim, the quote and the page, so the reader is taken to the text |
| Important clauses and obligations matter | Termination, payment, confidentiality, renewal and liability are identified and each is verified against its own evidence |
| Document-grounded Q&A | A question is answered from this document alone, or honestly declined |
| Evidence verification | The withheld count and the refused manipulations are the demonstration: the model proposed more than the user is shown |
| GenAI assists rather than replaces lawyers | The legal-information disclaimer is on every screen and in every answer |

**Not claimed, and not implemented:** contract comparison, document
summarisation, automatic legal advice, guaranteed risk detection, guaranteed
legal correctness, lawyer replacement, legal research, autonomous next-step
guidance, and visual `attention` badges.

---

## 10. Next recommended phase

Based on what this run actually showed, not on a plan made before it:

1. **Repeat the manual live run when the provider has capacity.** It is the one
   outstanding objective, it needs no code change, and §4's table is ready to
   be filled in. Try at a different time of day — the failures in Phases 15 and
   16 both occurred in the same part of the day.
2. **Then, and only then, decide whether to pin it as a live endpoint test.**
   That decision is about metered API usage, not about engineering, and it
   should be made with a successful run in hand.

Not recommended now, and deliberately not started: attention badges,
long-document chunking, accessibility work, CI, authentication, or any new
output surface. Item 1 is cheap and unblocks the honest presentation claim;
everything else can wait for its own evidence.

---

## 11. Final statement

What can be claimed after Phase 16:

> The demo document exists, is reproducible, and its expected grounding
> behaviour has been derived from the shipped verification code. The
> application's upload, extraction, coverage, workflow and failure-handling
> paths were exercised live through the real endpoints and behaved correctly,
> including a clean, typed, non-leaking refusal when the provider was
> unavailable.

What must **not** be claimed:

> That the Phase 15 output policy has been validated against live model output.
> It has not. One controlled attempt was made and the provider refused it.
