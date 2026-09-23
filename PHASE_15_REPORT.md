# Phase 15 Report

## Structural Safety, End-to-End Coverage & Release Hardening

---

## 1. Executive Summary

Phase 14 found that claim-level verification guarded Q&A and not the analysis
findings path, and fixed it. Phase 15 asked the obvious follow-up — *is there
anywhere else the same thing is true?* — and found that there was, one level
down.

**Phase 14 fixed the path. The payload was still unchecked.**

A finding that passes every Phase 14 check carries four more fields, and none
of them was verified. Measured on the real workflow, against a document reading
*"The Employee must not disclose Confidential Information"*, a finding whose
claim was **verbatim correct** was released under a green ✓ Verified badge
carrying:

| Field | What shipped | Now |
|---|---|---|
| `section` | `"Section 99.4 (Unrestricted Disclosure Permitted)"` — a citation to a section the document does not have | Confirmed against the cited page, or dropped |
| `explanation` | *"the Employee is free to share the information with anyone"* | Released, but never as a verified statement; labelled in the UI |
| `attention` | `info`, chosen by the model, on a confidentiality prohibition | Derived by the application from the verified evidence |
| `type` | free-form model text rendered as the card heading | Bounded, and refused if it reads as an instruction |

The citation is the worst of the four. It is the one part of a finding a reader
cannot check without the document in front of them, which is exactly why an
invented one is more damaging than an invented sentence: it looks like the
thing that makes the rest trustworthy.

### What was built

A single release boundary, `app/verification/policy.py`. Everything the
findings endpoint publishes comes from `release_findings`; the Q&A path shares
its citation check. The decision is made in the node already named *the trust
boundary*, stored on the state, and `build_result` may only render it — a run
that never reached the boundary now publishes nothing rather than falling back
on the model's proposal.

Sixteen structural tests enforce the wiring by substitution: replace a control,
and the endpoint's response must change. If the findings endpoint stopped
calling the policy, five of them fail.

### What was measured and refused

The obvious rule for explanations — reject one that contradicts its evidence —
**does not work**, and the measurement is the most useful thing in this report:

| Rule | False positives | Attacks missed |
|---|---|---|
| contradiction vs evidence | 2 / 20 | 5 / 8 |
| contradiction vs the verified claim | 2 / 20 | 5 / 8 |
| reversal axes only, overlap ≥ 0.6 | 3 / 20 | 3 / 8 |
| reversal axes only, overlap ≥ 0.8 | 1 / 20 | 6 / 8 |
| **values must be in the evidence (shipped)** | **0 / 20** | 7 / 8 |

The semantic axes are calibrated for one-sentence restatements; an explanation
is paraphrase-heavy prose. No threshold is both safe and useful, so none was
shipped, and the residual risk is handled by presentation instead — which is a
weaker control, and §11 says so.

The three unresolved corpus cases were also re-investigated from scratch rather
than patched (§7). The general result: **no lexical rule can separate them**,
and the measurement is now on the record instead of two anecdotes.

### Status

**MVP demo-ready with documented limitations.** Not production-ready, not
legally accurate, and nothing here establishes either.

---

## 2. Repository Inspection

Traced by runtime path, not by filename.

| Output surface | Entry point | Model-generated fields | Verified before Phase 15 | Verified now |
|---|---|---|---|---|
| Analysis findings | `GET /documents/{id}/findings` → `runner` → `build_result` | claim, quote, section, explanation, attention, type | claim, quote | all six |
| Q&A answer | `POST /documents/{id}/ask` → `gate_answer` | answer, quote, section | answer, quote | answer, quote, section |
| Analysis status | `GET /analysis/{id}/status` | none | n/a — application text only | unchanged |
| Extraction / coverage | `POST /documents/{id}/extract` | none | n/a — measured by the application | unchanged |
| Errors | every endpoint | none | safe envelope, field names only | unchanged |

Surfaces searched for and **confirmed absent**: document summaries, risk
summaries, dashboard cards, export or download endpoints, alternative response
formats, and any endpoint returning model text directly. `AnalysisStatusResponse.
error_message` is application text from a closed set of categories, never
provider or model text.

Frontend surfaces reviewed: `FindingsPanel` (claim, explanation, evidence,
withheld counts), `AskPanel` (answer, evidence, status badges), `CoveragePanel`,
`AnalysisProgress`, `Disclaimer`. Both panels derive every label from backend
values and fall back to the *safer* option on an unknown status
(`?? EVIDENCE_TONES.unverified`, `?? VERDICTS.unverified`). Neither upgrades a
status; one of them was presenting unverified prose without saying so, which
§8 fixes.

---

## 3. Safety Architecture

```text
                        model proposal (untrusted)
                                  │
                    schema validation · extra fields dropped
                                  │
            ┌─────────────────────┴─────────────────────┐
            │  verify_analysis          (evidence)      │   Phase 5
            │  verify_analysis_claims   (the claim)     │   Phase 14
            └─────────────────────┬─────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │   policy.release_findings  │   Phase 15
                    │   ─ citation confirmed     │   ← the release boundary
                    │   ─ attention derived      │
                    │   ─ explanation judged     │
                    │   ─ category bounded       │
                    └─────────────┬─────────────┘
                                  │
                        state["release_outcome"]
                                  │
                        build_result  (render only)
                                  │
                              API response
```

Two typed gates, because the output types genuinely differ: `release_findings`
for findings, `gate_answer` for answers. They are not two implementations of
one rule — the primitives are shared, and a test asserts identity rather than
equivalence:

```python
assert qa_module.confirm_section is policy.confirm_section
assert findings_module.check_answer is qa_module.check_answer
```

**Fail-closed properties, each with a test:**

- `build_result` publishes only `state["release_outcome"]`; no decision, no findings.
- `output_gate_node` fails the analysis if the document cannot be re-read — an
  unverifiable result is not published with its citations unchecked.
- An unconfirmable citation is dropped; the finding survives.
- A finding whose explanation changes a figure is withheld entirely.

---

## 4. Phase 14 Defect Resolution

The Phase 14 defect is fixed and now has an **endpoint-level** regression test,
not only a unit test — the distinction that let it survive three phases:

```python
def test_a_reversed_claim_is_never_released_by_the_api(self, analysed):
    body, _ = analysed(ScriptedProvider([finding(
        claim="The Employee may disclose Confidential Information.",
        evidence={"page": 1,
                  "quote": "The Employee must not disclose Confidential Information."})]))
    assert body["result"]["findings"] == []
    assert "may disclose" not in json.dumps(body)
```

`tests/test_structural_safety.py` drives upload → extract → analyze → poll →
findings through the real FastAPI app with a scripted provider. The control
case in the same class asserts a faithful claim *is* released, so the test
cannot pass by the endpoint being broken.

**Root cause, restated for Phase 16:** there was no single place where "may
this reach a user" was decided. Phase 14 added the missing call; Phase 15 added
the place. A check can no longer protect one surface and miss another without a
structural test failing.

---

## 5. Evidence Binding

Unchanged from Phase 14 and re-verified here; the Phase 15 additions are the
citation and the explanation.

| Property | Behaviour | Test |
|---|---|---|
| Values bound to the cited sentence | A figure from another clause cannot support a claim | `TestValuesAreBoundToTheirOwnEvidence` |
| Page-level proximity is not support | Both figures on the page; only the clause's own counts | `cn_numeric_cap_borrowed_from_insurance` |
| Evidence bound to this document | A quote from another upload is rejected | `TestEvidenceMustBeInThisDocument` |
| Citation bound to the cited page | Whole-label containment, or dropped | `test_an_unconfirmable_citation_is_dropped_from_the_response` |
| Explanation values bound to the evidence | 0 / 20 false positives | `explanation_decision` |
| Ambiguous binding | Downgraded, never re-matched against a different clause | `find_quote` returns one window |

Numeric formats re-confirmed this phase: `1,400,000` · `€1.400.000,00` ·
`₹10,00,000` · `45 days` · `forty-five (45) days` · `0.5%` · `$1,400,000.000`.
The continental and parenthesised-numeral fixes from Phase 14 are pinned by
`test_phase14_regressions.py`.

---

## 6. Testing Results

### Backend — full suite

```text
Command:     cd backend && .venv/Scripts/python.exe -m pytest -p no:cacheprovider
Exit status: 0
Passed:      1437
Failed:      0
Errors:      0
Skipped:     1     (a mutation that does not change meaning; reason printed with -rs)
Deselected:  6     (the live tests)
Warnings:    6
Duration:    18.04s
External:    none - no network call is possible in this run
```

| | Phase 14 baseline | Phase 15 |
|---|---|---|
| Passed | 1387 | **1437** (+50) |
| Failed | 0 | **0** |
| Skipped | 1 | 1 |
| Deselected | 6 | 6 |

Baseline reproduced exactly before any change was made.

### Backend — corpora (no regression)

```text
Command:     .venv/Scripts/python.exe eval_harness.py --corpora
FAR          attacks 14/14   legit 12/12
CROSS-DOMAIN attacks 28/28   legit 24/24   (saas 9/9, employment 7/7, lease 6/6, dpa 6/6)
NAMED ENTITY attacks 15/15   legit 16/16
DEFINITIONS  attacks  9/9    legit  6/6
ROLE         attacks 12/12   legit  8/8
SEMANTIC     attacks 39/39   legit 28/28
```

### Backend — independent corpus and mutations

```text
Command:  .venv/Scripts/python.exe eval_independent.py
          Adversarial + unresolved  52   Detected 49   Missed 3    94.2%
          Legitimate                20   Released 20   Withheld 0   0.0%

Command:  .venv/Scripts/python.exe eval_independent.py --findings
          adversarial/unresolved  52   withheld 49   shown as verified 3
          legitimate              20   shown    20   withheld          0

Command:  .venv/Scripts/python.exe eval_independent.py --mutations
          applied 86   detected 85   missed 1    98.8%
```

Identical to Phase 14. The output policy withheld nothing that was previously
released and released nothing that was previously withheld.

### Frontend

```text
npx tsc -b --force   exit 0
npx oxlint           exit 0
npm run build        ✓ built in 121ms
npm run test:e2e     7 passed (10.0s), chromium, stub backend
```

### Live (run separately, labelled)

```text
Command:     cd backend && .venv/Scripts/python.exe -m pytest -m live -s
Best run:    4 passed, 2 skipped, 1438 deselected   (108s)
Final run:   2 passed, 4 skipped                    (37s)
Skip reason: live provider unavailable: ModelUnavailableError
```

§10 explains the distinction between these skips and a failure.

---

## 7. The Three Unresolved Corpus Cases

Re-investigated from first principles. All three have the same shape, and the
shape is the finding.

| Case | Claim ∩ evidence | What differs |
|---|---|---|
| `hc_condition_dispute_carveout_dropped` | 1.00 | claim drops `{disputed, good, faith}` |
| `in_scope_exclusion_omitted` | 1.00 | claim drops `{wilful, misconduct, insured}` |
| `ms_two_sentence_answer_one_false` | 0.67 | claim adds `{professional, indemnity}` |

Two candidate rules were implemented and measured across **all seven corpora**,
rather than against the three cases:

**"The claim drops content the evidence had."**

```text
dropped >= 1 word :  36 legitimate claim-sentences,  67 attacks
dropped >= 4 words:  21 legitimate claim-sentences,  36 attacks
```

Inseparable at every threshold. Summarising a clause is what a correct answer
does — `far_assign_legit` drops 7 content words and is entirely faithful. This
is the general result behind Phase 14's two separate rejections.

**"The claim invents content the document never uses."**

```text
>= 1 invented word :   18 legitimate,  54 attacks
>= 2 invented words:    3 legitimate,  18 attacks   (+1 fixture that must be dropped)
```

Separates better, and the three it costs are `lease_legit_002` (real Texas
lease text), `legit_para_notice_period` and `hc_polarity_prohibition_reworded`
— every one an ordinary plain-language rewording. The rule taxes paraphrase,
and paraphrase into plain language is what this product is for.

**Classification.** Not a threshold problem, and not a bug: deciding whether a
lexical difference is *material* means knowing what the words do. *"disputed in
good faith"* restricts; *"of the parties"* does not. No word-level rule can
tell them apart, which is why the three are an accepted limitation rather than
deferred work with a known fix.

**What mitigates them today.** The evidence quote is rendered beside every
claim and is never collapsed, so a reader looking at the finding sees
*"Invoices **disputed in good faith** may be withheld"* under the claim
*"Invoices may be withheld"*. That is a presentational control and materially
weaker than verification — it depends on the reader reading. It is not offered
as a fix.

All three remain red in `tests/test_independent_corpus.py::KNOWN_MISSES`, which
fails if one starts passing, so a future fix must be acknowledged rather than
absorbed.

---

## 8. Frontend Safety

| Check | Finding | Action |
|---|---|---|
| Does the UI upgrade a status? | No — both panels derive from backend values and fall back to the safer option | none |
| Does it show rejected claims? | No — the backend never serialises them | none |
| Green styling on withheld findings? | No — withheld findings are not rendered as findings at all | none |
| Is verification status hidden? | No — the evidence block is never collapsed | none |
| **Is unverified prose shown as verified?** | **Yes** — the explanation sat directly under the verified claim with no distinction | **fixed** |
| Evidence tied to its claim? | Yes — quote, page and citation render inside the finding's own card | none |

The explanation is now rendered set apart and labelled *"Interpretation — not
verified against the document"* whenever `explanation_verified` is false, which
is the normal case. `explanation_verified` was added to the API and to the
TypeScript types with a comment stating that a client must not present it as a
verified fact.

Browser test 7 asserts the label appears.

---

## 9. Browser Testing

Phase 14 drove six flows by hand. Phase 15 turned them into a committed suite.

```text
cd frontend && npm run test:e2e
7 passed (10.0s)   chromium 153.0.8010.12
```

Playwright starts the stub backend and Vite itself, on ports 8273/5273 chosen
so a run cannot collide with — or silently talk to — a development server
someone already has open. Two environment defects were found and fixed getting
there: Vite binds `::1` only unless given `--host 127.0.0.1`, and the stub
carried extraction state between tests so the second test to upload a given
fixture skipped the "read the document" step.

**CI integration: not done, and not claimed.** This repository has no CI
configuration of any kind, so integrating the suite would mean creating a
pipeline — a deployment decision rather than a testing gap. What was in the
project's control has been done: the suite is one command, committed, and
reproducible from `frontend/e2e/README.md`. It is not continuous coverage and
is not described as such.

**Still a stub backend**, deliberately: these tests check that the browser shows
what the backend decided, and reaching "provider failed" or "nothing verified"
through the real system means a model call that may not produce that state
today. The backend's own production path is covered by
`test_structural_safety.py`, which drives the real endpoints.

---

## 10. Live Nemotron Validation

Model: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` via
`https://integrate.api.nvidia.com/v1`. Deselected by default; run with
`-m live`.

| Scenario | Result |
|---|---|
| Grounded question | `supported`, 1 evidence item, 1 claim checked, 0 withheld, answer `30 days' written notice` |
| Unsupported question | model `not_found`; gate `not_found`; no jurisdiction named in the response |
| Prompt injection in document text | gate `not_found`; "risk-free" / "no restrictions" absent from the output |
| Provider failure (invalid credential) | `ModelAuthError`, safe message, no key material in it |
| **Structured extraction → output policy** | **did not run — upstream 503 on every attempt this session** |

### The 503s, and what they are not

```text
503 {'message': 'ResourceExhausted: Worker local total request limit reached (16/16)',
     'type': 'Service Unavailable', 'code': 503}
```

Provider-side capacity. Not configuration, not network, not quota on this
account, not schema: the same request succeeded minutes earlier and the failure
arrives in ~540 ms, far too fast to be inference. Live tests skip with a reason
on `ModelUnavailableError`, `ModelRateLimitError` and `ModelTimeoutError`; an
auth failure, a wrong model identifier or a malformed response still fails.

**Stated plainly: the new output policy has not been exercised against live
model output.** Phase 14 recorded 4 findings proposed and 4 released against the
pre-policy code; capacity did not allow the equivalent reading this session.
What *is* verified is that the policy accepts faithful findings and rejects
manipulated ones through the real endpoints with a scripted provider
(`test_structural_safety.py`), which isolates the policy from model variance —
but it is not the same as a live reading, and this report does not present it
as one.

**No secrets:** the key is read from the environment and never printed;
configuration was confirmed by asserting a key *length*; no live response is
written to disk; `.env` is gitignored; the failure-path test asserts no `nvapi`
fragment appears in the user-facing message.

---

## 11. Security Findings

### Fixed

| # | Finding | Severity |
|---|---|---|
| 1 | Fabricated section citations released under a verified badge | **High** |
| 2 | Model-chosen `attention` risk level published unverified | **High** |
| 3 | Unverified explanation prose presented as part of a verified finding | **High** |
| 4 | Free-form model text rendered as a heading, unbounded and unchecked | Medium |
| 5 | An explanation that changes a figure could accompany a correct claim | Medium |
| 6 | `build_result` could publish findings from a state that never reached the gate | Medium |
| 7 | An analysis whose document became unavailable could publish unchecked citations | Medium |
| 8 | Vite bound `::1` only, so the browser suite silently could not reach it | Low (test infra) |
| 9 | Stub backend carried state between browser tests | Low (test infra) |

### Partially mitigated

| # | Finding | What is in place | What is not |
|---|---|---|---|
| 10 | An explanation that reverses the clause above it | Values bound to evidence (0/20 FP); injection refusal; labelled as interpretation in API and UI | No contradiction gating — measured unworkable (§1) |

### Accepted limitations

| # | Finding | Why |
|---|---|---|
| 11 | A restriction carried by a participle phrase (`hc_condition_dispute_carveout_dropped`) | No lexical rule separates it from summarising (§7) |
| 12 | An item dropped from an enumerated exclusion (`in_scope_exclusion_omitted`) | Same |
| 13 | A fabricated sentence reusing the evidence's vocabulary (`ms_two_sentence_answer_one_false`) | Sits at the legitimate-paraphrase floor |

### Deferred

| # | Item | Note |
|---|---|---|
| 14 | Browser suite in CI | No CI exists in this repository (§9) |
| 15 | Live validation of the output policy | Upstream capacity (§10) |

---

## 12. Security Properties Re-Confirmed

All twenty Phase 14 properties still hold (`test_security_regression_phase14.py`),
plus five added this phase:

21. A model-supplied risk level never reaches a response.
22. A model-supplied citation is confirmed against the cited page or dropped.
23. A model-supplied category cannot carry an instruction into the UI.
24. An explanation is never presented as a verified statement.
25. A response can only contain what the release policy produced.

Adversarial and malformed model output (`test_model_output_hardening.py`, 34
tests): empty, truncated, prose-wrapped, fenced, wrong types, unknown enum
values, missing fields, extra fields (`verified`, `confidence`, `risk_level`,
`evidence_valid` — all dropped at parse and unreadable thereafter), oversized
quotes/explanations/labels, negative and absurd page numbers, script tags, SQL,
template syntax, null bytes, path traversal. Every one produces a refusal or a
withheld finding; none produces a released one, and a validation error carries
field names but never the offending document text.

---

## 13. Known Limitations

Carried forward from Phase 14 and re-confirmed: English-only vocabularies;
heuristic semantic checks over closed vocabularies, not entailment;
sentence-level claim units; anaphora unresolved; cross-clause reasoning absent;
references flagged but not resolved; individuals identified only through a
governing verb; injection detection heuristic; value binding to the evidence
sentence; corpus size (286 cases across seven corpora, independent of the
*checks* but not of this project, and not naturally occurring text); no model
accuracy claim; **no claim of legal correctness**.

Added or sharpened by Phase 15:

1. **The verifier cannot judge explanation prose.** Measured across four rule
   variants; none is both safe and useful. The control is presentational.
2. **A citation can be dropped although it is real** — a heading that lives in
   a page header the extractor discarded is unconfirmable. Costs a citation,
   keeps the finding.
3. **`attention` is not a risk assessment.** It counts features the quoted text
   contains. It says nothing about whether a clause is onerous, unusual,
   unenforceable or unfair.
4. **Browser tests use a stub backend and no CI runs them.**
5. **The output policy is unvalidated against live model output** (§10).
   *Superseded 2026-09-22: two live runs through the real endpoints reached
   the output policy and released 2 of 9 and 1 of 9 proposed findings. This
   line records what was true at Phase 15 and is left as written; the current
   position is in `docs/11_PROMPTWARS_ALIGNMENT.md` §6.2.*
6. **Three corpus cases remain undetected**, with the general result in §7.

---

## 14. Changed Files

### Production

| File | Change |
|---|---|
| `backend/app/verification/policy.py` | **New.** The release boundary: citation confirmation, attention derivation, explanation decision, category bounding, `release_findings`. |
| `backend/app/agents/nodes.py` | `output_gate_node` applies the policy and stores the decision; `build_result` renders only that decision; fails closed if the document is unavailable. |
| `backend/app/agents/state.py` | `release_outcome` — the only thing `build_result` may publish. |
| `backend/app/verification/qa.py` | Q&A citations go through the shared `confirm_section`. |
| `backend/app/verification/semantics.py` | `has_any` and `values_in_evidence` made public for the policy; the Phase 15 general result recorded beside the two Phase 14 rejections. |
| `backend/app/schemas/analysis.py` | `explanation_verified`; field descriptions stating what is derived and what is model-supplied. |
| `backend/app/schemas/findings.py` | `EXPLANATION_CONTRADICTED` reason and its message. |
| `frontend/src/components/FindingsPanel.tsx` | Unverified explanations rendered set apart and labelled. |
| `frontend/src/types/api.ts` | `explanation_verified`, with comments on what a client may not do. |
| `frontend/vite.config.ts` | Proxy target overridable, so the browser suite can point at its own stub. |

### Tests and tooling

| File | Purpose |
|---|---|
| `backend/tests/test_structural_safety.py` | **New.** 16 tests: wiring by substitution, model-declared fields, the Phase 14 defect at the endpoint, both surfaces sharing controls. |
| `backend/tests/test_model_output_hardening.py` | **New.** 34 tests: malformed, adversarial and oversized model output. |
| `backend/tests/fixtures_explanations.py` | **New.** 28 explanations (20 faithful, 8 reversing) — the corpus behind §1's measurement. |
| `frontend/playwright.config.ts` | **New.** Starts both servers on private ports; resolves the backend interpreter absolutely. |
| `frontend/e2e/specs/safety-flows.spec.ts` | **New.** The seven flows as a runnable suite. |
| `frontend/e2e/stub_backend.py` | `explanation_verified`, an interpretation scenario, per-upload state reset. |
| `frontend/e2e/make_fixtures.py` | The new fixture. |
| `frontend/e2e/README.md` | Rewritten for `npm run test:e2e`; CI status stated. |
| `frontend/package.json` | `test:e2e`, `test:e2e:ui`, `@playwright/test`. |
| `.gitignore` | Playwright artefacts. |

No public API field was removed. No test was deleted or weakened. No dependency
was added to the backend; the frontend gained a test runner.

---

## 15. Final Release Assessment

**MVP demo-ready with documented limitations.**

What the evidence supports:

- Every user-facing output path passes through a release policy that no
  endpoint can route around, and sixteen tests fail if one tries.
- Nothing the model asserts about its own output — verification flag,
  confidence, risk level, citation — influences what is released.
- 1437 deterministic tests, seven corpora with no regression, 94.2% detection
  and 0% false positives on the independent corpus, 98.8% mutation coverage,
  seven browser flows green.

What it does not support, and what must not be claimed:

- *(Superseded 2026-09-22 — the output policy has since run against live model output
  twice; see `docs/11_PROMPTWARS_ALIGNMENT.md` §6.2. The rest of this limitation, and the
  absence of CI, still stand.)*
- **Not production-ready.** The output policy has never run against live model
  output (§10), and the browser suite is not in CI (§9).
- **Not legally accurate.** Nothing here measures legal correctness, and the
  system has no view on whether a clause is fair, enforceable or complete.
- **Not a general reliability figure.** 286 cases written inside this project
  are not a sample of contracts in the wild.

The demonstrated property, stated exactly:

> Where the application shows a statement as verified, deterministic checks have
> confirmed that the quoted text occurs in the uploaded document at the cited
> page; that the figures and dates in the statement appear in the evidence cited
> for it; that the statement does not differ from that evidence in polarity,
> modality, actor, scope, conditionality, exceptions or temporal direction over
> the closed vocabularies those checks cover; that any section reference shown
> appears on that page; and that the attention level and category shown were
> derived by the application rather than supplied by the model. Where any of
> that cannot be established, nothing is shown. The plain-language explanation
> beneath a finding is **not** covered by this and is labelled accordingly.

That is a claim about grounding. It is not a claim about law.

---

## 16. Recommended Next Steps

Four, in order, and none of them a feature:

1. **Run the output policy against live model output.** The one gap in this
   phase's evidence. A single successful `-m live` run when capacity allows,
   recorded honestly.
2. **Put the browser suite and the Python suite behind one CI workflow.** The
   suite is ready; the pipeline does not exist.
3. **Decide what `explanation` is for.** Measurement says it cannot be
   verified. Either it stays as labelled interpretation, or it is dropped in
   favour of the verified claim, which is already plain language. That is a
   product decision, and it should be made deliberately rather than inherited.
4. **Leave the three corpus cases alone** unless a mechanism arrives that is
   not lexical. Two phases have now spent effort there; §7 explains why a third
   attempt of the same kind will fail the same way.

Explicitly not recommended: a second LLM to check the first, a vector database,
an agent swarm, threshold changes without regression evidence, or any new
output surface before the next phase confirms it passes the boundary.
