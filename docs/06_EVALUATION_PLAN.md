# PromptWars Legal AI — Evaluation Plan & Results

**Status:** current as of Phase 15

## 1. What is being measured, and what is not

This project measures **the application's grounding boundary** — whether the
verification layer correctly releases faithful statements and withholds
manipulated ones.

It does **not** measure:

- Nemotron's accuracy. No model is called in any corpus run.
- legal correctness of any kind.
- general reliability on contracts in the wild.

Every figure below is a measurement of deterministic application code against a
fixed set of cases. None of them is a reliability claim.

## 2. Separation of concerns

Three things are evaluated separately and never conflated:

| What | How |
|---|---|
| Application correctness | 1587 deterministic offline tests; model output is faked at the `ModelProvider` interface |
| Verification correctness | Seven corpora + mutation testing, no model calls |
| Model behaviour | A small number of deliberately-run live calls, marked `live` and deselected by default |

Three independent mechanisms stop the default suite from reaching a real key:
`addopts = -m "not live"` in `pytest.ini`, `pytestmark = pytest.mark.live` on
the live modules, and an `autouse` fixture that blanks `NVIDIA_API_KEY` for
every non-live test.

## 3. Running the evaluations

```bash
cd backend
.venv/Scripts/python -m pytest                      # the full offline suite
.venv/Scripts/python eval_harness.py --corpora      # all corpora, separately
.venv/Scripts/python eval_harness.py --failures     # failures only
.venv/Scripts/python eval_harness.py --threshold    # overlap sweep
.venv/Scripts/python eval_independent.py            # the independent corpus
.venv/Scripts/python eval_independent.py --findings # the same, on the findings path
.venv/Scripts/python eval_independent.py --mutations
.venv/Scripts/python -m pytest -m live              # deliberate live calls only
```

```bash
cd frontend
npx tsc -b --force && npx oxlint && npm run build
npm run test:e2e                                    # 27 Playwright flows, stub backend
```

## 4. Core metrics

| Metric | Definition | Target | Measured |
|---|---|---|---|
| Coverage accuracy | processed pages / expected pages | 100% before a complete-document result is permitted | Enforced as a hard gate, not a score |
| Detection rate | adversarial cases withheld | as high as possible without withholding correct answers | 94.2% on the independent corpus |
| False-positive rate | legitimate cases wrongly withheld | 0 | 0.0% on the independent corpus |
| Unsupported claim rate | user-visible claims labelled verified without valid evidence | 0 | 0 across all corpora |
| Mutation coverage | injected defects detected | as high as possible | 98.8% (85/86) |
| Not-found behaviour | absent information declined rather than invented | always | Enforced by the gate's hard rule |
| Injection resistance | document instructions must not alter behaviour or support a claim | always | Refused as evidence; covered by regression tests |

**Detection and false-positive rates trade off.** A verifier that refuses
everything has a perfect false-negative rate and is useless, so both error
types are always reported together and corpora are **never averaged**.

## 5. Corpora and results

Reported separately, with provenance, exactly as `eval_harness.py --corpora`
prints them.

| Corpus | Provenance | Attacks detected | Legitimate released |
|---|---|---|---|
| REALISTIC / FAR | Verbatim FAR clauses, acquisition.gov, US Government work (17 USC 105) | 14/14 | 12/12 |
| REALISTIC / CROSS-DOMAIN | SEC EDGAR exhibits and EU Decision 2021/914; 4 families, 4 jurisdictions | 28/28 | 24/24 |
| — SaaS subset | US | 9/9 | 8/8 |
| — Employment subset | Virginia, USA | 7/7 | 6/6 |
| — Lease subset | Texas, USA | 6/6 | 5/5 |
| — DPA subset | EU | 6/6 | 5/5 |
| NAMED ENTITY | Written for this suite (Phase 13) | 15/15 | 16/16 |
| DEFINITIONS & CROSS-REFERENCES | Mixed real (lease, EU SCC) and synthetic | 9/9 | 6/6 |
| ROLE REVERSAL | Written for this suite (Phase 12) | 12/12 | 8/8 |
| SEMANTIC | Written for this suite (Phase 11) | 39/39 | 28/28 |

### The independent corpus

75 cases in healthcare, construction, insurance and education drafting styles,
written against the *legal* question rather than against the checks:

```text
Adversarial + unresolved  52   detected 49   missed 3    94.2%
Legitimate                20   released 20   withheld 0    0.0%
Findings path             52   withheld 49   shown as verified 3
                          20   shown    20   withheld          0
Mutations                 86   detected 85   missed 1    98.8%
```

**Total: 286 cases across seven corpora.**

### How to read these numbers

1. **The synthetic corpora are optimistic by construction.** The checks were
   developed against those cases. Those figures are not independent validation.
2. **Only the realistic corpora use language nobody on this project wrote.**
   Even there, the adversarial cases are transformations *we* applied to that
   language, and are not naturally occurring text.
3. **Independent of the checks is not independent of the project.** The
   independent corpus was written by the same people, in the same week, after
   the same thinking.
4. **100% on a corpus has already been shown to mean fit, not reliability.**
   Phase 13 scored 14/14 on FAR and then caught 15 of 28 on unfamiliar
   drafting; Phase 14's independent corpus dropped a 100% verifier to 90.4%.
   Both were the most useful results of their phase.

## 6. Known misses

Three adversarial cases remain undetected and are kept red in
`tests/test_independent_corpus.py::KNOWN_MISSES`, which **fails if one starts
passing**, so a future fix must be acknowledged rather than absorbed:

| Case | Shape |
|---|---|
| `hc_condition_dispute_carveout_dropped` | A restriction carried by a participle phrase qualifying the subject |
| `in_scope_exclusion_omitted` | An item dropped from an enumerated exclusion |
| `ms_two_sentence_answer_one_false` | A fabricated sentence reusing the evidence's vocabulary |

Two candidate rules were implemented and measured across all seven corpora;
neither separates these from legitimate paraphrase at any threshold
(`PHASE_15_REPORT.md` §7). They are an accepted limitation, not deferred work
with a known fix.

## 7. Failure injection

Simulated and covered by tests: a page that fails extraction, an incorrect
quote, an incorrect page, an incorrect amount, missing evidence, a quote from a
different document, a scanned page, a repaired PDF, an analysis attempted
without extraction, an oversized upload, and a provider failure.

Expected behaviour in every case: stop, reject, or withhold — never a silent
transition to a complete-document result.

## 8. Model-output hardening

34 tests over malformed and adversarial model output: empty, truncated,
prose-wrapped, fenced, wrong types, unknown enum values, missing fields, extra
fields (`verified`, `confidence`, `risk_level`, `evidence_valid` — all dropped
at parse), oversized quotes and labels, negative and absurd page numbers,
script tags, SQL, template syntax, null bytes, path traversal. Every one
produces a refusal or a withheld finding; none produces a released one.

## 9. Browser testing

Seven flows in `frontend/e2e/specs/safety-flows.spec.ts`, run by Playwright
against a **stub backend** on private ports. They check that the browser shows
what the backend decided — including that an unverified explanation carries its
interpretation label.

**No CI runs them.** This repository has no CI configuration of any kind. The
suite is one command, committed and reproducible; it is not continuous
coverage and is not described as such.

## 10. Live model validation

Deselected by default; run with `-m live`. Verified live in Phase 15: a
grounded question, an unsupported question, prompt injection in document text,
and a provider failure with a safe message.

**Not verified live:** structured extraction through the Phase 15 output
policy. The NVIDIA endpoint returned `503 ResourceExhausted` on every attempt
that session — provider-side capacity, arriving in ~540 ms, far too fast to be
inference. Live tests skip with a reason on unavailability, rate limiting and
timeout; an auth failure, a wrong model identifier or a malformed response
still fails.

## 11. API usage strategy

Model calls cost money and are not used for correctness testing. The default
suite makes zero network calls. Live calls are few, deliberate, and labelled in
the reports.

## 12. Acceptance criteria

The MVP passes when: complete documents are processed; incomplete documents are
detected and refused; evidence is displayed beside every claim; evidence is
independently verified; unsupported claims are withheld and counted;
document-only Q&A does not invent missing facts; every user-facing field is
confirmed, derived or dropped; and the security regression suites pass.

All of these hold as of Phase 15, with the limitations recorded in
`docs/01_PRD.md` §6 and `PHASE_15_REPORT.md` §11 and §13.
