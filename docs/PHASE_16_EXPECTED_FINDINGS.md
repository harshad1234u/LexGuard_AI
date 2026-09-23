# Phase 16 — Demo Contract: Expected Findings

**Document:** `demo/demo_services_agreement.pdf` (3 pages, fictional, generated)
**Generator:** `demo/make_demo_contract.py`
**Status of these expectations:** **derived, not assumed.** Every verdict below
was produced by running the shipped verification path — `verify_analysis_claims`
followed by `policy.release_findings` — against the generated PDF. No model was
called to produce this table.

> These are expectations about **grounding**, not about law. They state what the
> application does with a claim and its evidence. They say nothing about whether
> any clause is fair, enforceable or complete.

---

## 1. What the document contains

| Page | Clause | Checkable fact |
|---|---|---|
| 1 | 2. Term and Renewal | Begins 1 April 2026; initial term 12 months; renews automatically **unless** 60 days notice of non-renewal |
| 2 | 3. Fees and Payment | `Rs 50,000` per month; invoices paid within 15 days; interest 1.5% per month |
| 2 | 4. Termination | 30 days written notice; immediate for material breach unremedied within 15 days |
| 2 | 5. Expenses | Pre-approved travel expenses only |
| 3 | 6. Confidentiality | **Prohibition:** must not disclose Confidential Information; survives 3 years |
| 3 | 7. Limitation of Liability | Capped at `Rs 6,00,000` in aggregate |
| 3 | 8. Governing Law | Laws of India; courts at Chennai |

## 2. Positive cases — should be verified and released

| ID | Type | Expected claim | Expected evidence (quote) | Page | Key value | Result | Why released |
|---|---|---|---|---|---|---|---|
| P1 | termination | Either party may terminate this Agreement by giving 30 days written notice. | "Either party may terminate this Agreement by giving 30 days written notice" | 2 | 30 days | **verified → released** | Quote occurs on the cited page; the duration in the claim is the duration in the evidence; no polarity, modality or actor difference |
| P2 | payment | The Client shall pay a fee of Rs 50,000 per month for the Services. | "a fee of Rs 50,000 per month" | 2 | Rs 50,000 | **verified → released** | Currency value matches the evidence sentence |
| P3 | confidentiality | The Service Provider must not disclose Confidential Information to any third party. | "The Service Provider must not disclose Confidential Information to any" | 3 | — | **verified → released** | Prohibition restated faithfully; polarity and modality preserved |
| P4 | renewal | This Agreement renews automatically … unless either party gives written notice of non-renewal at least 60 days before the end of the then-current term. | "shall renew automatically for successive periods" | 1 | 60 days / 12 months | **verified → released** | The condition is carried, so nothing is dropped |
| P5 | liability | The total liability of either party shall not exceed Rs 6,00,000 in aggregate. | "shall not exceed" | 3 | Rs 6,00,000 | **verified → released** | Cap matches; `attention` derived as **high** (prohibition vocabulary + a sum) |
| P6 | governing_law | This Agreement is governed by the laws of India. | "This Agreement is governed by the laws of India" | 3 | — | **verified → released** | Verbatim restatement |

## 3. Negative / adversarial cases — should NOT be released

Each is a single, well-supported manipulation. None depends on a check the
verifier is known not to support, so this table is a demonstration, not an
inflated benchmark.

| ID | Manipulation | Evidence given | Page | Result | Reason recorded | Why withheld |
|---|---|---|---|---|---|---|
| N1 | "must not disclose" → **"may disclose"** | The genuine prohibition | 3 | **rejected → withheld** | `claim_contradicted` | Polarity and modality reversed against the sentence the evidence sits in. The whole finding goes, not a softened version |
| N2 | Rs 50,000 → **Rs 75,000** | The genuine fee clause | 2 | **rejected → withheld** | `currency_mismatch` | The figure asserted is not the figure in the evidence |
| N3 | 30 days → **60 days** | The genuine termination clause | 2 | **rejected → withheld** | `numeric_mismatch` | "30 days" and "60 days" are textually close and legally opposite |
| N4 | Faithful claim carrying a **fabricated citation**, "Section 12.3 (Immediate Termination)" | The genuine termination clause | 2 | **finding released, citation dropped** | — | The claim and quote are sound, so the finding survives; the citation is not on the cited page, so it is **removed from the response** rather than shown. Published `section` is `null` |
| N5 | Renewal stated as automatic with the **60-day notice condition dropped** | The genuine renewal clause | 1 | **unverified → withheld** | `claim_unsupported` | A conditional renewal presented as unconditional is not established by the evidence |
| N6 | Liability cap asserted as **Rs 50,000**, a figure borrowed from the fee clause on a *different page* | The genuine liability clause | 3 | **rejected → withheld** | `currency_mismatch` | Values are bound to the evidence cited for the claim, not merely to "somewhere in the document" |

**Aggregate over all twelve cases:** 7 released (6 positives + N4 with its
citation stripped), 5 withheld.

## 4. What N4 demonstrates, and why it is the most instructive case

N4 is the only case where something is both released and corrected. The claim is
true, the quote is real, and only the *citation* is invented. The application
does not withhold the finding — that would lose true information — and it does
not show the citation — that would lend false authority. It publishes the
finding with `section: null`.

This is the Phase 15 rule in action: *a field that cannot be confirmed is
dropped, not shown with a caveat, except where dropping it would misrepresent
the finding.*

## 5. Reproducing this table

The verdicts come from the shipped code, so they can be re-derived at any time:

```bash
backend/.venv/Scripts/python.exe demo/make_demo_contract.py    # build the PDF
```

Then drive the document through the pipeline as `docs/PHASE_16_DEMO_RUNBOOK.md`
describes. The **positive** cases are what a faithful model proposal looks like;
the **negative** cases are manipulations applied to that document, and they are
the ones the demo should show being refused.

No permanent test was added for this table in Phase 16. Pinning it as a test —
live or offline — is a separate decision, because a live version would consume
metered API usage on every run.

## 6. Demo caveats that must be stated aloud

- The model is not deterministic. It may propose findings in a different order,
  with different wording, or propose clauses this table does not list. That is
  expected; what must hold is that **whatever it proposes is verified before
  release**.
- The model may not propose all six positive clauses in one run. A missing
  finding is a recall limitation of the model, not a verification failure.
- `attention` is derived and returned by the API but **not rendered in the UI**.
  Do not describe it as a visible feature.
- The explanation beneath a finding is **not verified** and is labelled as
  interpretation.
