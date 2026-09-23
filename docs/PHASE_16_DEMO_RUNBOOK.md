# Phase 16 — Demo Runbook

How to run the PromptWars Legal AI demonstration end to end, what to expect at
each step, and what must be said aloud about the system's limits.

**Companion documents:** `docs/PHASE_16_EXPECTED_FINDINGS.md` (what the demo
document should produce) and `docs/PHASE_16_REPORT.md` (what the live
validation actually showed).

---

## 0. Before the demo

| Check | Command | Expect |
|---|---|---|
| Model key configured | `GET /api/v1/health` | `"model_provider_configured": true` |
| Offline suite green | `cd backend && .venv/Scripts/python.exe -m pytest` | `1587 passed` |
| Demo PDF exists | see §2 | 3 pages |

**Provider capacity is the one thing you cannot control.** The NVIDIA hosted
endpoint has returned `503 ResourceExhausted` in Phase 15 and again in Phase 16
(see the report). It fails in about one second, so you will know immediately.
Have the fallback in §9 ready.

## 1. Start the backend

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

The key is read from `.env` server-side. It is never sent to the browser and
never appears in a response or a log.

## 2. Generate the demo contract

The repository does not carry PDFs (`.gitignore` excludes `*.pdf`), so the
document is built from its source script:

```bash
backend/.venv/Scripts/python.exe demo/make_demo_contract.py
# wrote demo/demo_services_agreement.pdf (3 pages)
```

The contract is fictional, marked as a demonstration document on page 1, and
contains no real party, person, address or confidential information. Its
clauses are listed in `docs/PHASE_16_EXPECTED_FINDINGS.md` §1.

## 3. Start the frontend

```bash
cd frontend
npm install     # first time only
npm run dev     # http://localhost:5173, proxies /api to port 8000
```

## 4. The demo sequence

Either drive it in the browser, or use the API directly. Both exercise the same
path — the frontend performs this sequence and nothing else.

### In the browser

1. Open `http://localhost:5173`.
2. Upload `demo/demo_services_agreement.pdf`.
3. Press **Read the document** (extraction). The coverage panel reports
   3 of 3 pages processed, `complete`.
4. Press **Analyze**. The progress panel walks the workflow stages.
5. Findings appear with their quote, page and confirmed citation; withheld
   statements appear as counts with a plain-language reason.
6. Ask a question in the Ask panel, e.g. *"What is the termination notice
   period?"*

### By API

```bash
BASE=http://127.0.0.1:8000/api/v1
PDF=demo/demo_services_agreement.pdf

curl -s -X POST $BASE/documents/upload -F "file=@$PDF;type=application/pdf"
#   -> 201, document_id, page_count: 3, status: validated, source_repaired: false

curl -s -X POST $BASE/documents/$DOC/extract          # per-page manifest + coverage
curl -s $BASE/documents/$DOC/status                   # analysis_eligible: true
curl -s -X POST $BASE/documents/$DOC/analyze          # 202 + analysis_id  (ONE inference)
curl -s $BASE/analysis/$AID/status                    # poll: queued -> running -> completed|failed
curl -s $BASE/documents/$DOC/findings                 # the gated result
curl -s -X POST $BASE/documents/$DOC/ask -H 'Content-Type: application/json' \
     -d '{"question":"What is the termination notice period?"}'
curl -s -X DELETE $BASE/documents/$DOC                # discard immediately
```

**When polling, read the analysis object's own `status`.** The response also
contains a `coverage.status` whose value is `complete`; a naive parser that
takes the first `"status"` it finds will report success while the analysis has
actually failed. This caught the Phase 16 validation script and is worth
knowing before you write anything against this API.

## 5. Monitoring progress

`stage` names the step the workflow is **entering**: `queued`, `validating`,
`ingesting`, `checking_coverage`, `building_document_map`, `analyzing`,
`verifying`, `gating_output`, `done`. A client sitting on `analyzing` is
waiting for the model, which is the slow step.

`status` is `queued`, `running`, `completed` or `failed`. `completed` is set
only once the output gate has run.

## 6. What to expect

Per `docs/PHASE_16_EXPECTED_FINDINGS.md`: the six positive clauses verify and
release; the six manipulations are refused, except the fabricated citation,
where the finding survives and the citation is dropped.

**The model is not deterministic.** It may return findings in a different order
or wording, or miss a clause. That is a model recall limitation, not a
verification failure. What must hold is that everything shown was verified and
everything unverified was withheld and counted.

## 7. Demonstrating the differentiator

The most convincing part of this demo is not the findings list — it is what the
system refuses to show.

1. **Show a verified finding** with its quote and page beneath the claim.
2. **Show the withheld count** and say what it means: the model proposed more
   than you are seeing, and the rest could not be grounded.
3. **Ask a question the document does not answer**, e.g. *"What is the notice
   period for a data breach?"* The system answers in its own voice — *"I
   couldn't find this information in the uploaded document"* — rather than
   guessing. Say why the wording is careful: it reports that nothing could be
   **confirmed**, not that the clause does not exist.
4. **Point at the interpretation label** under an explanation and say that the
   application does not claim to have verified that sentence.

## 8. Limitations to state during the demo

Do not wait to be asked:

- This provides **legal information**, not legal advice. It does not replace a
  lawyer and does not guarantee legal correctness.
- The plain-language **explanation is not verified** — it is labelled as
  interpretation.
- **`attention` is API-only.** The backend derives it; the UI does not render
  it. There are no attention badges.
- **Not implemented:** contract comparison, document summaries, checklists,
  next-step guidance, lawyer-preparation packs, DOCX, OCR.
- A **scanned PDF is refused**, by design — an image-only page means the text
  was not captured, so no complete-document analysis is offered.
- The system is **demo-grade**: no authentication, no rate limiting, in-process
  job execution, and no CI.
- Evaluation figures measure the **application's grounding boundary**, not the
  model's accuracy and not legal correctness.

## 9. If the provider is unavailable

The failure is fast (about one second) and surfaces as
`error_category: "provider_unavailable"` with the safe message *"The analysis
service is temporarily unavailable."*

**Do not retry in front of an audience** — there are no automatic retries by
design, and hammering a capacity-limited endpoint will not help.

Fall back to what does not need the provider, all of which still demonstrates
the core argument:

1. **Upload, extraction and the coverage gate** — entirely local, no model.
   Upload a scanned or truncated PDF and show the analysis being refused.
2. **The offline suite** — `pytest`, 1587 tests, ~107 seconds.
3. **The evaluation corpora** — `eval_harness.py --corpora` and
   `eval_independent.py`, which run the real verification stack with no model
   call and print both error rates.
4. **The browser suite** — `npm run test:e2e`, 27 safety flows.

Say plainly that the model call is unavailable and that the verification layer
is what you are showing. That is an honest demo of the part this project
actually built.
