# PromptWars Legal AI — Implementation Record (Phases 1–15)

**Status:** Phases 1–15 complete. MVP demo-ready with documented limitations.

> This document was originally a forward-looking build sequence numbered
> Phase 0–10. That numbering was superseded during the build. What follows is
> the **delivered** record, using the phase numbers the reports and the root
> `README.md` use. Where a planned item was not built, it says so.

---

## Phase 0 — Repository setup

```text
backend/   FastAPI + Python
frontend/  React + Vite + TypeScript + Tailwind
docs/      specification and decision records
```

Backend stack: FastAPI, Pydantic, PyMuPDF, LangChain, LangGraph,
`langchain-nvidia-ai-endpoints`, httpx, pytest. Frontend stack: React 19,
Vite, TypeScript, Tailwind CSS v4, oxlint, Playwright (added in Phase 15).

## Phase 1 — Repository and environment setup

Project skeleton, configuration loaded from the environment only,
`.env.example`, secret hygiene, logging, the error envelope and its stable
codes.

## Phase 2 — Document upload and validation

`POST /documents/upload`. Validation order: filename safety → size →
extension → MIME type → file signature → parseability. PDF only; DOCX is
rejected rather than half-supported. Structural repair by PyMuPDF is detected
and flagged, because a reconstructed page count cannot support the coverage
invariant.

**Deliverable:** an untrusted file is either rejected with a stable code, or
accepted with an application-established page count.

## Phase 3 — PDF extraction and page manifest

`POST /documents/{id}/extract`, `GET /documents/{id}/manifest`. Page-level text
extraction via PyMuPDF, per-page status (`processed`, `empty`, `unreadable`,
`failed`), text length and image count. Entirely local; no model involved.

**Deliverable:** `PDF → manifest + page text`.

## Phase 4 — Coverage controller

`app/verification/coverage.py`. `complete` requires all of: pages exist, every
page processed, no failed pages, no unreadable pages, and the source was not
repaired. `require_complete_coverage()` is the hard gate.

**Deliverable:** for a 50-page PDF the application knows, from its own
counters, whether 50 of 50 pages were captured. The model is never asked.

## Phase 5 — Deterministic evidence verification

`app/verification/grounding.py` and `numeric.py`. Evidence present → page
exists → quote occurs there → values agree, with a polarity guard. Statuses:
`verified`, `partially_verified`, `unverified`, `rejected`.

**Deliverable:** `model finding → verified | partially_verified | unverified | rejected`.

## Phase 6 — Nemotron integration

`app/models/`: the abstract `ModelProvider`, `NemotronProvider`, the prompt
contract, the untrusted-content payload builder, and a safe error taxonomy.
Key handling, redaction and no-retry behaviour are covered by tests.

**Deliverable:** `document pages → structured model proposal`.

## Phase 7 — Controlled LangGraph workflow

`app/agents/`: the seven-node graph, the failure-ends-the-run edge rule, the
coverage edge that makes the model node unreachable without complete coverage,
and the in-process asynchronous runner.

**Deliverable:** `validate → ingest → coverage_gate → document_map → model → verify → output_gate`.

## Phase 8 — End-to-end journey

`upload → status → extract → status → analyze → poll → findings`, driven
through the public API by `tests/test_end_to_end.py` including the paths that
must stop: a scanned page, an analysis without extraction, an oversized upload,
a provider failure, and a run where nothing survives verification. The React
frontend performs the same sequence and nothing else.

## Phase 9 — Document-grounded Q&A

`POST /documents/{id}/ask`. Synchronous, one question, one document. Reuses the
Phase 4 coverage gate and the Phase 5 verifier unchanged; adds
`verification/qa.py` and `schemas/qa.py`. No RAG, no embeddings, no vector
database, no chat history.

**Deliverable:** a verified answer with page-cited evidence, or an honest
"not found".

## Phase 10 — Semantic grounding and security hardening

Measured the Phase 9 boundary and found it insufficient: a verified quote does
not verify the prose built on it. Added claim-level checks on four axes —
polarity, modality, actor, conditions — plus refusal of evidence that is text
addressed to the assistant.

## Phase 11 — Evaluation expansion and false-positive analysis

An expanded corpus (67 cases) measured a 35.1% false-negative rate against the
Phase 10 checks. Four axes added: certainty, scope, temporal direction, time
limits, plus reference-only evidence. Measured false-negative rate fell to
7.7% on the same corpus, with no legitimate case withheld — a figure that is
optimistic by construction, since the checks were developed against those cases.

## Phase 12 — Real contract text and role binding

Verbatim US Federal Acquisition Regulation clauses — language nobody on this
project wrote — found three failures the synthetic corpus never did.
`acting_party()` added to bind who performs an action, catching role reversal.
A dependency parser was measured against the deterministic patterns first and
had nothing left to contribute, so no NLP dependency was added.

## Phase 13 — Cross-domain validation and named entities

Against real SaaS, employment, lease and data-processing clauses the Phase 12
verifier caught 15 of 28 adversarial cases. Two latent defects were the cause:
substring vocabulary matching (`all` inside `shall`) and a dot inside a number
ending a sentence. Both fixed. `named_parties()` closed the named-company
reversal gap that Phase 12 had declared out of reach.

## Phase 14 — Independent adversarial validation

A 75-case corpus in four unfamiliar contract families, plus an audit asking of
every check whether it actually influences what a user is shown.

**The audit found the most serious defect in the project: claim-level semantic
verification was never on the analysis path.** It guarded Q&A only. A finding
whose claim reversed its own quote was returned as `verified` under a green
badge with the contradicting quote printed underneath. `verification/findings.py`
closed this by running the *same* implementations the Q&A gate runs, so the two
surfaces cannot drift apart. Five further checks were added (relatedness,
claim-level values, carve-outs, reported speech, contradictory definitions) and
two candidate fixes were written, measured and **reverted** because they
withheld correct answers about real contract text.

## Phase 15 — Structural safety and release hardening

Asked the follow-up question — *is the same thing true anywhere else?* — and
found it one level down, in the payload rather than the path. Four fields
reached users unchecked: the model's section citation, its explanation, its
chosen attention level, and the free-form category rendered as a heading.

Built `app/verification/policy.py`, the single release boundary, enforced by
sixteen structural tests that fail if an endpoint routes around it. Measured
and **refused** contradiction gating on explanations: four variants, none both
safe and useful; the residual risk is handled by a UI label, which is weaker
and is recorded as such. Committed a seven-flow Playwright suite.

---

## Current state

| Measure | Value |
|---|---|
| Backend tests | 1587 passed, 1 skipped, 6 deselected (live), 0 failed |
| Evaluation corpora | 7 corpora, 286 cases, no regression |
| Independent corpus | 94.2% detection, 0.0% false positives, 3 known misses kept red |
| Mutation coverage | 98.8% (85/86) |
| Frontend | `tsc -b` clean, `oxlint` clean, build clean, 27 Playwright flows green |
| Live validation | Partial — the output policy has run against live model output (2 successful runs, 2026-09-22, releasing 2 of 9 and 1 of 9 proposed findings). Repeatability unmeasured: 2 of 6 attempts that day. No live Q&A success observed; the overview not yet rendered in a browser from a live analysis |
| CI | None configured |

## Not built

Two-document comparison · document summaries · checklists · export/download ·
options or next-steps guidance · briefing packs for a lawyer · DOCX ·
OCR fallback · multilingual output · clause navigation · dark mode ·
authentication · persistence · CI pipeline · a deployment manifest.

See `docs/11_PROMPTWARS_ALIGNMENT.md` for how these relate to the problem
statement, and `docs/01_PRD.md` §5 for the full list.

## Recommended next steps

From `PHASE_15_REPORT.md` §16, in order, none of them a feature:

1. Run the output policy against live model output and record the result.
2. Put the browser suite and the Python suite behind one CI workflow.
3. Decide what `explanation` is for — labelled interpretation, or dropped in
   favour of the verified claim, which is already plain language.
4. Leave the three known corpus misses alone unless a non-lexical mechanism
   arrives.

Explicitly not recommended: a second LLM to check the first, a vector database,
an agent swarm, threshold changes without regression evidence, or any new
output surface before it is confirmed to pass the release boundary.
