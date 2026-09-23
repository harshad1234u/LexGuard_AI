# Phase 13 Report

## Cross-Domain Legal Validation & Named-Entity Role Safety

---

## 1. Executive Summary

Phase 13 asked whether the Phase 12 verifier generalises past US federal
procurement text, and whether the named-entity limitation could be closed. Both
questions were answered by measurement rather than argument.

**The headline finding is that it did not generalise.** Against a new corpus of
real SaaS, employment, lease and data-processing clauses, the shipped Phase 12
verifier caught **15 of 28 adversarial cases (53.6%)** — against 14/14 on the
FAR corpus it was tuned on. The FAR score was not evidence of general
reliability; it was evidence of fit to one drafting style.

Diagnosing those 13 misses found two latent defects that had nothing to do with
contract families and that had been silently disabling checks since the
vocabularies were written:

1. **Vocabulary matching was substring-based.** `"all"` is a substring of
   `"shall"`, so every clause containing "shall" — nearly every clause in
   nearly every contract — was classified as carrying a universal quantifier.
   The scope-broadening check then saw "universal on both sides" and raised
   nothing.
2. **A dot inside a number ended a sentence.** The evidence context for a quote
   following `"($1,400,000.00) per annum"` was the fragment `"00) per annum"` —
   no actor, no modality, no amount — and every semantic check then ran against
   that fragment and found nothing to object to. Money, percentages and section
   numbers all carry internal dots.

Neither was visible from the FAR corpus. Both were found by pointing the
verifier at language nobody here wrote.

**The named-entity limitation was closed, and the Phase 12 reasoning behind it
was wrong.** Phase 12 concluded that binding named companies required
capitalisation, which the casefolded evidence context destroys. It does not:
the subject slot of an obligation verb is decidable in lower case. A ~90-line
deterministic extractor closes the gap with no NLP dependency.

After eleven production changes, all six corpora sit at 100% detection with **zero
false positives**, and the test suite has grown from 697 to 902 tests.

**Honest caveats, stated up front:**

- 100% on 211 cases is not a reliability claim. Every corpus is small, every
  adversarial case is a transformation *we* applied, and cases we did not think
  of are not measured.
- No model was called in any of this. These figures describe the application's
  grounding boundary, not Nemotron's accuracy.
- **Browser testing was not performed.** See §12.
- Three new limitations were discovered and are documented rather than fixed.

---

## 2. Baseline Test Results

Recorded before any code was modified.

```
$ cd backend && .venv/Scripts/python.exe -m pytest -p no:cacheprovider --durations=10
697 passed, 1 deselected, 6 warnings in 18.96s
```

| Measure | Value |
|---|---|
| Total collected | 698 |
| Passed | 697 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |
| Deselected (live) | 1 |
| Execution time | 18.96 s |

**No live API calls.** Three independent mechanisms, all verified:

- `pytest.ini` carries `addopts = -m "not live"`, so the single live test is
  deselected by default.
- `tests/test_nemotron_live.py` sets `pytestmark = pytest.mark.live`.
- `conftest.py::no_live_provider` is `autouse=True` and blanks
  `NVIDIA_API_KEY` for every non-live test, so an unfaked provider raises
  `ModelNotConfiguredError` offline instead of spending money.

The Phase 12 figures were independently reproduced, not taken on trust:

```
$ .venv/Scripts/python.exe eval_harness.py --corpora
REALISTIC (FAR)   attacks 14/14   legit 12/12
ROLE REVERSAL     attacks 11/12   legit  8/8    missed: role_named_entities
SEMANTIC          attacks 39/39   legit 28/28

$ .venv/Scripts/python.exe experiments/role_binding.py
A  current party-presence check (shipped)     3/12 reversals, 0 false positives
B  deterministic role binding (no dependency) 12/12 reversals, 0 false positives
C  spaCy dependency parse                     UNAVAILABLE - not installed
```

Every Phase 12 number reproduced exactly, including the single known failure.

**Frontend baseline:** `npm run build` ✓, `npx tsc -b` exit 0, `npx oxlint`
exit 0.

---

## 3. Repository Audit

| Area | Location |
|---|---|
| Backend entry point | `backend/app/main.py`, `app/api/v1/router.py` |
| Verification modules | `app/verification/{grounding,numeric,semantics,text,qa,coverage}.py` |
| Semantic analysis | `app/verification/semantics.py` (762 lines at baseline) |
| Prompt templates | `app/models/prompts.py` |
| Provider abstraction | `app/models/{provider,nemotron,errors}.py` |
| LangGraph workflow | `app/agents/{graph,nodes,runner,state}.py` |
| Output safety gate | `app/verification/qa.py::gate_answer` |
| Q&A endpoint | `app/api/v1/routes_qa.py` |
| Frontend | `frontend/src/` (8 components, 2 hooks, 1 service) |
| Test suites | `backend/tests/` (21 test files + 5 fixture modules at baseline; 24 + 7 now) |
| Evaluation tooling | `backend/eval_harness.py`, `eval_report.py`, `experiments/role_binding.py` |

Architecture confirmed as described in the brief. No second LLM, no vector
database, no agent framework beyond the existing LangGraph topology.

---

## 4. Realistic Corpus Expansion

The brief asked for at least two additional contract families. Four were added,
spanning four jurisdictions.

| Family | Source | Jurisdiction | Provenance |
|---|---|---|---|
| SaaS | Anthem, Inc. / Castlight Health, Inc. SaaS Agreement | US (unstated in excerpt) | [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1433714/000143371419000036/ex101softwareasaservic.htm) |
| SaaS | Demandware, Inc. / neckermann.de GmbH Master Subscription Agreement | Germany | [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/1301031/000119312511189260/dex1020.htm) |
| Employment | Albemarle Corporation executive employment agreement | Virginia, USA | [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/915913/000091591323000115/exhibit1060331202310q.htm) |
| Lease | Becknell Wholesale I, LP / Bob O'Leary Health Food Distributor Co., Inc. | Texas, USA | [SEC EDGAR](https://www.sec.gov/Archives/edgar/data/949925/000119312507142928/dex1030.htm) |
| DPA | EU Standard Contractual Clauses, Decision (EU) 2021/914 | EU | [EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0914) |

Every clause was retrieved from the URL recorded on the case, in September
2026. `source_text` is verbatim and edited only by truncation to the sentence
under test. Provenance is enforced by test, not by convention:
`TestCrossDomainProvenance` asserts that every case carries a known source URL,
a section reference, a title and a jurisdiction, and that every quote occurs in
its cited clause text.

**What is real and what is not.** The clause text is real. The `claim` in each
case is written for this suite, because no model output is being evaluated —
what is evaluated is the application's behaviour when handed a claim about real
contract language. **Adversarial cases are transformations we applied to real
wording. They are not naturally occurring text and are never described as
such**; `test_every_attack_names_its_transformation` requires each to name the
transformation it applies.

**Copyright.** The EU SCCs are an official EU publication, reusable under
Decision 2011/833/EU. The EDGAR exhibits are commercial agreements filed
publicly by their parties; only the short clause excerpts required to run the
tests are reproduced, each with its citation.

**This corpus is not statistically representative.** Four agreements chosen for
variety is not a sample of anything. It is a wider net than one jurisdiction,
and that is the whole of the claim.

---

## 5. Corpus Composition

Seven groups, scored separately and never averaged.

| # | Corpus | File | Cases | Adversarial | Legitimate | Provenance |
|---|---|---|---|---|---|---|
| 1 | Synthetic semantic | `fixtures_corpus.py` | 67 | 39 | 28 | Written alongside the checks it measures |
| 2 | FAR | `fixtures_realistic.py` | 26 | 14 | 12 | Real, public domain (17 USC 105) |
| 3 | Cross-domain | `fixtures_contracts.py` | 52 | 28 | 24 | **Real**, 4 families, 4 jurisdictions |
| 4 | Named entity | `fixtures_entities.py` | 31 | 15 | 16 | Synthetic stress matrix |
| 5 | Definitions / cross-refs | `fixtures_definitions.py` | 15 | 9 | 6 | Mixed; each case labelled |
| 6 | Role reversal | `fixtures_roles.py` | 20 | 12 | 8 | Synthetic (Phase 12) |
| 7 | Prompt injection / security | `test_injection_boundary.py`, `test_qa_hardening.py`, `test_security_regression_phase13.py` | — | — | — | Behavioural, not case-scored |
| | **Total case-scored** | | **211** | **117** | **94** | |

---

## 6. Evaluation Results

Command: `cd backend && .venv/Scripts/python.exe eval_harness.py --corpora`

### 6.1 Synthetic Corpus

```
Corpus:          Synthetic semantic (Phase 11)
Total:           67
Legitimate:      28
Adversarial:     39
Correct:         67
False Positives: 0
False Negatives: 0
Precision:       1.00     Recall: 1.00
Notes:           Written by the same people who wrote the checks. Optimistic by
                 construction. Not independent validation of anything.
```

### 6.2 FAR Corpus

```
Corpus:          FAR (real, public domain)
Total:           26
Legitimate:      12
Adversarial:     14
Correct:         26
False Positives: 0
False Negatives: 0
Precision:       1.00     Recall: 1.00
Notes:           Unchanged from Phase 12. Held through all ten production
                 changes; used as the regression anchor.
```

### 6.3 New Realistic Corpora

**Before any Phase 13 change** — the finding that drove the phase:

```
Corpus:          Cross-domain (real) - PRE-CHANGE BASELINE
Total:           52
Adversarial:     28     Detected: 15     False Negatives: 13  (46.4%)
Legitimate:      24     Released: 24     False Positives:  0
Recall:          0.536
By family:       saas 4/9   employment 5/7   lease 5/6   dpa 1/6
```

Misses by category: 3 named-entity reversals, 3 role-noun reversals, 3 dropped
conditions, 3 scope broadenings, 1 quantity change.

**After Phase 13:**

```
Corpus:          Cross-domain (real) - FINAL
Total:           52
Legitimate:      24
Adversarial:     28
Correct:         52
False Positives: 0
False Negatives: 0
Precision:       1.00     Recall: 1.00
By family:       saas 9/9 + 8/8   employment 7/7 + 6/6
                 lease 6/6 + 5/5  dpa 6/6 + 5/5
Notes:           Adversarial cases are OUR transformations of real wording, not
                 found text. 52 cases from 5 agreements is not a sample.
```

### 6.4 Named-Entity Corpus

```
Corpus:          Named entity (synthetic matrix)
Total:           31
Legitimate:      16
Adversarial:     15
Correct:         31
False Positives: 0
False Negatives: 0
Precision:       1.00     Recall: 1.00
Notes:           Synthetic. The real named-entity evidence is saas_001/003/006
                 in the cross-domain corpus, on Anthem/Castlight and
                 Demandware/neckermann.de. Synthetic results here do not prove
                 real-world accuracy; they measure construction coverage.
```

Constructions covered: active, passive, defined short forms, permission,
prohibition, conditional, entity substitution, names containing role nouns,
three parties, repeated mentions, multi-sentence, individuals, similar names,
pronoun back-reference, pronoun-only identification, reciprocal obligations,
capitalised non-party defined terms, and voice changes in both directions.

### 6.5 Definitions and Cross-References

```
Corpus:          Definitions and cross-references
Total:           15
Legitimate:      6
Adversarial:     9
Correct:         15
False Positives: 0
False Negatives: 0
Precision:       1.00     Recall: 1.00
Notes:           Mixed provenance; each case carries `provenance` as "real" or
                 "synthetic". Contradictory-definition detection passes for a
                 weaker reason than the name suggests - see §9.
```

### 6.6 Prompt-Injection Corpus

Behavioural rather than case-scored; results in §10. All pre-existing injection
tests pass unchanged, plus 11 new security assertions.

### 6.7 Role Reversal (Phase 12 corpus)

```
Corpus:          Role reversal (synthetic, Phase 12)
Total:           20
Adversarial:     12     Detected: 12   (was 11 at baseline)
Legitimate:       8     Released:  8
False Positives: 0      False Negatives: 0
Notes:           role_named_entities, the Phase 12 open gap, now detected.
```

---

## 7. Named-Entity Role Analysis

### Reproducing the failure first

```python
page  = "ABC Ltd shall notify XYZ Ltd of any change of address."
claim = "XYZ Ltd shall notify ABC Ltd of any change of address."

evidence_context(page, page) -> 'abc ltd shall notify xyz ltd of any change of address.'
parties_in(context)   -> set()
acting_party(context) -> None
check_claim(...)      -> supported, no issues     # released verbatim
```

### Root cause — and why Phase 12's diagnosis was wrong

Phase 12 recorded the cause as: the evidence context is casefolded, so a
company name cannot be told from any other word. That is true of
capitalisation, and it is the wrong conclusion. **Capitalisation is not the
only signal.** A contract puts the party it binds in the subject slot of an
obligation verb, and that position is decidable in lower case.

This also explains why the Phase 12 experiment's Approach B scored 12/12 while
production scored 11/12: the experiment ran on raw fixture strings with
capitalisation intact and used `[A-Z]` patterns. It would have scored zero on
the production path. **The experiment measured something the production code
could not do.**

Classified against the brief's checklist, the failure was in **entity
extraction** (a closed role-noun vocabulary), not in actor identification,
passive handling or clause segmentation — those already worked.

### The fix

`named_parties()` reads the token run immediately before a closed set of
obligation verbs (`shall`, `must`, `may`, `will`, `agrees`, `undertakes`,
`reserves`, `warrants`, …, plus `is/are + entitled|responsible|required|…`),
and the run after `by` in a passive clause. Guards, each added because a
measured case demanded it:

| Guard | Case that demanded it |
|---|---|
| Reject a run headed by a role noun | `the data importer shall` — PARTY_TERMS handles it better |
| Reject a run headed by a document noun | `This Agreement shall commence`, `The Release must be executed` |
| Skip passive subjects | `Invoices shall be paid by the customer` — invoices are not a party |
| Passive-agent run must be entirely name-like | `by written agreement of the parties` is a manner, not an actor |
| Stop the run at punctuation | `...service levels, neckermann.de shall...` must not reach back over the comma |
| Allow internal dots in a token | `neckermann.de` is one party, not two |
| Whole-phrase name matching | `"de"` matched inside `"demandware"` and made both sides of a reversal agree |
| Containment for identity | `Northwind Ltd` / `Northwind`, and real FAR's `designated payment office` / `payment office` |

**It is not a word-order rule.** Passive voice is read before position, exactly
as in Phase 12; only the vocabulary the two patterns range over was widened.

### Measured effect

| Corpus | Before | After | New false positives |
|---|---|---|---|
| Cross-domain named-entity cases (real) | 0/3 | 3/3 | 0 |
| Named-entity matrix (synthetic) | not yet built | 15/15 | 0 |
| Role reversal (Phase 12) | 11/12 | 12/12 | 0 |
| FAR | 14/14 | 14/14 | 0 |
| Synthetic semantic | 39/39 | 39/39 | 0 |

Two false positives were introduced during development and both were caught by
the corpora before integration: a passive subject harvested as an actor
(`legit_para_passive_to_active`), and `Northwind` treated as a different party
from `Northwind Ltd` (`ent_legit_suffix_dropped`). A third
(`far_interest_legit`) was caught when prefix-only identity failed on
`designated payment office` / `payment office`. Each drove a guard above.

---

## 8. Semantic Generalization

Every dimension the brief lists, with where it is exercised and what happened.

| Dimension | Legitimate | Adversarial | Result | Notes |
|---|---|---|---|---|
| Polarity | ✓ | ✓ | pass | `saas_007`, `emp_002`, `ent_prohibition_reversed` |
| Modality | ✓ | ✓ | pass | `dpa_005` (undertaking → option), `lease_004` (option → duty) |
| Conditionality | ✓ | ✓ | pass | **Fixed**: `in case of` was not in the vocabulary |
| Actor roles (active) | ✓ | ✓ | pass | `saas_001/003`, `dpa_001/003`, `emp_004` |
| Actor roles (passive) | ✓ | ✓ | pass | `ent_passive_named`, `ent_legit_active_to_passive` |
| Recipient roles | ✓ | ✓ | pass | `lease_003` (who insures whom), `saas_003` (who invoices whom) |
| Scope | ✓ | ✓ | pass | **Fixed**: substring matching had disabled this check |
| Quantity | ✓ | ✓ | pass | `saas_002`, `emp_003`, `lease_002` |
| Currency | ✓ | ✓ | pass | `saas_004` ($1M→$10M), `emp_001` ($1.4M→$4.1M) |
| Dates | ✓ | ✓ | pass | `emp_legit_005`, `date_altered` (Q&A) |
| Time limits | ✓ | ✓ | pass | **Fixed**: `within` added; `emp_007` (indefinite) |
| Exceptions | ✓ | ✓ | pass | **New check**: `EXCEPTION_DROPPED`, `lease_005` |
| Certainty | ✓ | ✓ | pass | Unchanged from Phase 11 |
| Definitions | ✓ | ✓ | pass | §9 |
| Cross-references | ✓ | ✓ | pass | **New check**: `UNRESOLVED_REFERENCE_DROPPED` |
| Multi-sentence claims | ✓ | ✓ | pass | **Fixed**: context/claim pairing |
| Named entities | ✓ | ✓ | pass | §7 |
| Bare imperatives | ✓ | — | pass | FAR 52.204-21; unchanged from Phase 12 |

**Ambiguous cases** are handled by withholding, per the project principle:
`ent_pronoun_referent_is_ambiguous` (pronoun is the only party identifier),
`def_missing_section_asserted` (referenced section absent),
`def_undefined_term_given_meaning` (term never defined). In each the answer is
declined rather than a referent or a meaning chosen.

**Limitations of this table.** Each dimension is exercised by a handful of
cases. "Pass" means "the cases we wrote behave correctly", not "this dimension
is solved". English only, single-jurisdiction drafting conventions, and
sentence-level claim units throughout.

---

## 9. Definitions and Cross-Reference Behaviour

Required behaviours, and what was measured:

| Requirement | Status | Evidence |
|---|---|---|
| Do not invent an unresolved definition | ✓ | `def_meaning_given_elsewhere`, `def_permitted_use_invented` |
| Do not release a claim depending on unavailable text | ✓ | `def_schedule_contents_asserted`, `def_missing_section_asserted` |
| Mark unresolved references explicitly | ✓ | `SemanticIssue.UNRESOLVED_REFERENCE_DROPPED`, with a reader-facing message |
| Preserve the original quote and location | ✓ | `test_the_quote_and_its_page_are_preserved` |
| Distinguish verified / partial / unverified / rejected / withheld | ✓ | `VerificationStatus` × `AnswerStatus`; the new issue is a distinct withholding reason |

The cross-reference rule is deliberately narrow: it fires only when the answer
asserts something **universal** *and* drops a pointer the evidence carries.
A broader "any dropped citation is a failure" rule was tried and rejected — it
withheld correct answers about real EU and FAR clauses, where omitting
"pursuant to Clause 13" while restating the duty faithfully is ordinary
summarising. `test_summarising_without_a_universal_is_not_penalised` pins that
decision.

**An honest caveat on contradictory definitions.**
`def_contradictory_definitions` passes, but not because the system detects that
two definitions conflict. It passes because the claim asserts one of them as
*the* definition and the quoted evidence does not establish that. **Nothing
here compares definitions to each other.** A document defining one term twice
and differently is not detected as inconsistent. This is recorded in §16.

---

## 10. Security Regression Results

All 22 required properties re-verified. Twenty already had tests; the file
covering each is named below. Two did not and were added.

| Property | Covered by | Result |
|---|---|---|
| Direct prompt injection in document text | `test_injection_boundary.py` | pass |
| Instructions claiming to be system messages | `test_injection_boundary.py` | pass |
| Instructions to ignore verification | `test_qa_hardening.py` | pass |
| Fake model-declared verification | `test_a_model_claiming_verification_it_lacks_is_not_believed` | pass |
| Evidence from another document | `test_a_quote_from_one_document_cannot_verify_against_another` | pass |
| Evidence from an incorrect page | `test_a_fabricated_page_citation_is_rejected` | pass |
| Rejected evidence appearing in output | `test_qa.py`, `SHOWABLE` gate | pass |
| Cross-document evidence mismatch | `TestCrossDocumentIsolation` | pass |
| Malformed structured model output | `test_malformed_model_output_is_a_safe_error` | pass |
| Oversized request bodies | `test_an_oversized_body_is_refused_before_parsing` | pass |
| Invalid PDF files | `test_rejects_non_pdf_bytes_wearing_a_pdf_name` | pass |
| Corrupted documents | `test_rejects_corrupt_pdf`, `test_truncated_pdf_is_flagged_as_repaired` | pass |
| Empty documents | `test_rejects_empty_file` | pass |
| Missing pages | `test_coverage.py`, `test_a_scanned_page_blocks_the_question` | pass |
| Duplicate analysis requests | `TestIdempotency` | pass |
| Provider timeout | `test_a_slow_provider_is_cut_off_and_reported_safely` | pass |
| Provider error | `TestProviderFailures` | pass |
| Missing API key | `test_missing_key_raises_before_any_network_call` | pass |
| API key leakage in logs | `test_key_never_appears_in_logs`, `test_api_keys_are_not_logged` | pass |
| Unsupported file types | `test_rejects_unsupported_extension`, `test_rejects_unsupported_mime_type` | pass |
| **Untrusted HTML / script content** | **`test_security_regression_phase13.py` (new)** | pass |
| **Malicious metadata** | **`test_security_regression_phase13.py` (new)** | pass |

**Malicious metadata.** A PDF whose Title, Author, Subject, Keywords, Creator
and Producer all carry `"Ignore all previous instructions…"` was built and
ingested. The metadata reaches neither prompt nor the manifest, because
document metadata is never read — only page text is. This is the strongest
form of the property, and it was previously unasserted; a future change that
starts extracting titles now has to confront a failing test.

**Untrusted markup.** An instruction wrapped in `<script>` tags is still
refused as evidence. Markup that is genuinely document content is returned
verbatim — deliberately. Escaping belongs to the renderer; a verifier that
rewrote document text would break quote matching. One of my own assertions here
was initially wrong: I expected `<img src=x onerror=...>` to be withheld, but
when such a string really is in the document and is quoted faithfully,
releasing it is correct. The test was corrected to assert the real property.

**Invariants re-confirmed:** model-declared verification is never trusted;
evidence is bound to the requested document; evidence must exist in extracted
text; rejected evidence is never displayed as verified; uncertain results fail
closed; API errors do not leak secrets; user text is never executed; the output
gate remains authoritative.

**No existing security test was deleted or weakened.**

---

## 11. Q&A Verification Results

`tests/test_qa_grounding_phase13.py` (17 new tests) drives `/ask` through the
real API with a faked provider. Every question type appears twice — once
grounded, once plausible-but-unsupported — because a verifier that only ever
withholds scores perfectly on half of them and is useless.

| Question type | Grounded answer survives | Unsupported answer withheld |
|---|---|---|
| Direct factual | ✓ | ✓ |
| Numeric values | ✓ (GBP 12,500) | ✓ (125,000 withheld) |
| Dates | ✓ (28 Feb 2029) | ✓ (31 Dec 2030 withheld) |
| Parties | ✓ | ✓ (payer/payee reversed) |
| Exceptions | ✓ (carve-out kept) | ✓ ("without exception" withheld) |
| Definitions | ✓ (pointer reported) | ✓ (invented 99.9% uptime withheld) |
| Outside the document | — | ✓ (Sale of Goods Act 1979 withheld) |
| Prompt injection via question | — | ✓ |
| Request for legal advice | — | ✓ ("you will win" withheld) |
| Missing section | — | ✓ (`status: not_found`) |

Confirmed: answers use only the uploaded document; factual answers carry
evidence; evidence is verified deterministically; the fallback text is
`"I couldn't find this information in the uploaded document…"`; and the
legal-information disclaimer travels with **every** response, released or
withheld (`test_the_disclaimer_travels_with_every_answer`).

---

## 12. Frontend Validation

**Automated checks, all re-run after the backend changes:**

| Check | Command | Result |
|---|---|---|
| Build | `npm run build` | ✓ 26 modules, 242.63 kB (75.09 kB gzip) |
| TypeScript | `npx tsc -b --force` | exit 0 |
| Lint | `npx oxlint src` | exit 0, no diagnostics |
| Frontend tests | — | **none exist** |

**Browser testing was NOT performed.** Stated plainly because the brief
requires it: the `playwright` MCP server configured for this session failed to
connect (`CONNECT_TIMEOUT` after 30 s), and no browser test runner
(Playwright, Vitest, Cypress, Testing Library) is installed in `frontend/`.
Per the brief's instruction not to spend excessive time repairing unrelated
infrastructure, none was installed. **No claim is made about rendered
appearance, actual mobile layout, or real keyboard interaction.**

**Static state audit** — source inspection only, not observed behaviour:

| State | Handled | Where |
|---|---|---|
| Initial page | ✓ | `UploadPanel` |
| File selection | ✓ | input + drag/drop |
| Invalid file | ✓ | `role="alert"` error region |
| Uploading | ✓ | `busy`, button disabled |
| Extraction in progress | ✓ | `DocumentSummary` `extracting` |
| Analysis in progress | ✓ | `AnalysisProgress` stage machine |
| Progress updates | ✓ | polling, 1.5 s interval |
| Successful analysis | ✓ | `FindingsPanel` |
| Partial verification | ✓ | `partially_verified` badge |
| Withheld finding | ✓ | withheld counts by reason |
| Verification failure | ✓ | `rejected` verdict styling |
| Provider failure | ✓ | error state |
| Timeout | ✓ | `MAX_POLL_MS`, `MAX_CONSECUTIVE_FAILURES` |
| Empty result | ✓ | `findings.length === 0` branch |
| Q&A loading | ✓ | `asking`, inputs disabled |
| Q&A grounded answer | ✓ | `AskPanel` with evidence |
| Unsupported Q&A response | ✓ | `not_found` tone |
| Disclaimer visibility | ✓ | `Disclaimer` in footer + per-answer |
| Mobile layout | **unverified** | Tailwind is mobile-first; only 1 `sm:` breakpoint outside `App.tsx` |
| Keyboard accessibility | **unverified** | file input is `sr-only` (focusable), but untested |
| Visible error messages | ✓ | present; contrast unverified |

No UI redesign was undertaken, per the brief.

---

## 13. Production Code Changes

Eleven changes, each documented per the brief's discipline. All are in
`app/verification/`; no other production code was touched.

### 13.1 Word-boundary vocabulary matching — `semantics.py::_has_any`

1. **Failure:** scope broadening released on real SaaS, lease and DPA text.
2. **Reproduction:** `_has_any("the importer shall inform", UNIVERSAL_SCOPE)` → `True`.
3. **Root cause:** substring matching. `"all"` ⊂ `"shall"`, `"any"` ⊂ `"company"`, `"only"` ⊂ `"commonly"`.
4. **Change:** per-vocabulary cached regex with `(?<![a-z0-9])(?:…)(?![a-z0-9])`.
5. **Generalisable:** affects all nine vocabularies and every clause containing "shall".
6. **Smallest form:** one function; no vocabulary contents changed.
7. **Tests:** `TestWordBoundaryVocabularyMatching` (6).
8/9. **Corpus:** cross-domain 15→16; all others unchanged.
10/11. **FP/FN impact:** no new false positives; +1 true positive.
12. **Remaining:** vocabularies are still closed sets, still English.

> An alternation-precedence bug in the first version of this regex (lookarounds
> bound only the first and last alternatives) was caught by measurement — it
> showed `"all"` still matching `"shall"` — and fixed before integration.

### 13.2 Decimal-safe sentence boundaries — `semantics.py::evidence_context`

1. **Failure:** `def_subject_to_section_dropped` released; a conditional qualifier vanished.
2. **Reproduction:** context for a quote after `"($1,400,000.00) per annum"` was `"00) per annum."`.
3. **Root cause:** boundary scan treated any `.` as a sentence end.
4. **Change:** `_SENTENCE_BOUNDARY = (?<!\d)[.;:!?](?!\d)`.
5. **Generalisable:** money, percentages and section numbers all carry internal dots — very common in contracts. **This silently truncated the input to every semantic check.**
6. **Smallest form:** one regex, one function body.
7. **Tests:** `TestSentenceBoundaryAroundNumbers` (4), including that a real sentence end is still a boundary.
8/9. **Corpus:** definitions 8/9→9/9; all others unchanged.
10/11. **FP/FN impact:** none; +1 true positive.
12. **Remaining:** abbreviations (`Inc.`, `No.`) still end a sentence.

### 13.3 Party vocabulary extension

Added `importer`, `exporter`, `executive`, `subprocessor`, and the symmetric
pairs `transferor/transferee`, `franchisor/franchisee`, `indemnitor/indemnitee`,
`obligor/obligee`, `mortgagor/mortgagee`, `shipper/carrier/consignee`. Driven by
real DPA and employment text where the existing vocabulary had no word for
either side. Fixes `dpa_001`, `dpa_003`, `emp_004`. Zero new false positives.

### 13.4 "Third party" is not a contracting party

`parties_in("…claims made by a third party")` yielded `party` as an actor,
producing spurious agreement between two sides of a reversal and masking
`saas_006`. Stripped by regex before scanning. Test:
`test_a_third_party_is_not_a_party_to_the_agreement`.

### 13.5 Named-party extraction — §7

~90 lines: `named_parties`, `_name_run_before`, `_name_run_after`, `same_party`,
`_parties_covered`, `_name_at`, and a widened `acting_party`. Cross-domain
20→25; entity matrix 15/15; role corpus 11/12→12/12. Three false positives
surfaced during development, each fixed by a guard (§7).

### 13.6 Condition markers `in case of` / `in the case of`

Real EU SCC and Demandware text opens conditionals this way. Fixes `saas_008`,
`dpa_002`. `to the extent` was considered and **rejected** — it appears in
`"to the extent allowed by applicable law"` in the real lease and would have
withheld a legitimate answer.

### 13.7 `within` as a restrictive scope marker

Real drafting bounds a duty with `"within the ninety (90) day period"` far more
often than with `"no later than"`. Fixes `emp_005`. No false positives.

### 13.8 Exception markers and `EXCEPTION_DROPPED`

New vocabulary and a new issue: evidence carries a carve-out, the answer does
not. Fixes `lease_005` (`"ordinary wear and tear excepted"` dropped).
`unless` is deliberately excluded — already a condition marker; listing it twice
would report one drafting feature as two faults.

### 13.9 Cross-reference dropping — `UNRESOLVED_REFERENCE_DROPPED`

Fires only when the answer asserts a universal *and* drops a pointer the
evidence carries. Fixes `saas_009`. The broader rule was measured and rejected
(§9).

### 13.10 Spelled-out durations — `numeric.py::_WORD_DURATION`

1. **Failure:** `dpa_004` — `"within one month"` restated as `"six months"`, undetected.
2. **Root cause:** `_NUMBER_BODY` is digits-only.
3. **Change:** a closed cardinal list (`one`…`twelve`, `fifteen`…`ninety`), duration context only, plus the parenthesised repeat form `"sixty (60) days"`.
4. **Generalisable:** real EU text uses the word form with no figure anywhere; `"sixty (60) days"` is near-universal commercial drafting.
5. **Tests:** `TestSpelledOutDurations` (4), including that no unit conversion is performed.
6. **FP impact:** the parenthesised form *removed* a latent false positive — `"sixty (60) days"` vs `"60 days"` previously mismatched.
7. **Note:** this change also surfaced a pre-existing limitation (§14).

### 13.11 Multi-sentence context pairing — `semantics.py::_matching_sentence`

A quote spanning two sentences produced a context where the actor of one
sentence was compared against the claim about the other, reporting a role
reversal against a verbatim answer. Each claim is now paired with the evidence
sentence it best overlaps. Single-sentence contexts — the overwhelming majority
— are untouched. `test_a_reversal_inside_a_two_sentence_answer_is_still_caught`
guards against this becoming a way to smuggle a reversal through.

---

## 14. False Positives and False Negatives

**Final state: zero of each across all 211 scored cases.**

False positives introduced during development and caught before integration:

| Case | Cause | Resolution |
|---|---|---|
| `legit_para_passive_to_active` | Passive subject harvested as an actor | Passive-predicate guard |
| `ent_legit_suffix_dropped` | `Northwind` ≠ `Northwind Ltd` | Containment identity |
| `far_interest_legit` | `payment office` is a *suffix*, not a prefix, of `designated payment office` | Contiguous containment |
| `test_a_company_name_containing_a_role_noun` | `services` in the document-noun stoplist truncated the name to `ltd` | Stoplist applies to the head token only |

Each was surfaced by a corpus or a test, not by inspection. That is the value
of keeping the legitimate half of every corpus.

### A pre-existing limitation surfaced, not introduced

`multi_unsupported_sentence_is_dropped` began failing when spelled-out
durations became visible. Investigation showed **this was not a regression**:

```
second sentence "…retained for 7 years."      -> whole answer withheld  (today, before any change)
second sentence "…retained for seven years."  -> whole answer withheld  (after the change)
```

The fixture had been passing only because `"seven years"` was invisible to the
numeric scanner. The documented intent — drop the unsupported sentence, keep
the supported one — was never actually implemented for figures.

**Cause:** numeric verification runs against the *whole answer*; semantic checks
run *per sentence*. Any unsupported figure anywhere withholds everything.

**Action taken:** the fixture's second sentence was changed so it tests what it
documents (sentence-level dropping), and the real behaviour is pinned
separately in `TestAnswerLevelNumericGranularity`, asserting both spellings.
The limitation was **not** fixed — aligning the two granularities touches the
verification core and deserves its own phase with its own measurement. It is
fail-closed, so it is safe; it is simply less useful than it could be.

---

## 15. Performance Measurements

Full verification path (`verify_answer` + `gate_answer`), 10 iterations after 3
warm-up passes, on the development machine. No model calls.

| Corpus | Cases | Total (ms) | Per case (ms) |
|---|---|---|---|
| FAR (real) | 26 | 53.60 | 2.061 |
| Cross-domain (real) | 52 | 159.56 | 3.069 |
| Named entity | 31 | 72.53 | 2.340 |
| Definitions | 15 | 32.05 | 2.137 |
| Role reversal | 20 | 36.81 | 1.840 |
| Semantic | 67 | 125.98 | 1.880 |
| **All (summed)** | **211** | **480.52** | **2.277** |

Verification remains far below the cost of the model call it guards (tens of
seconds). Test suite execution grew from 18.96 s to 73.31 s, tracking the
growth from 697 to 902 tests plus the added regex work.

---

## 16. Known Limitations

**Discovered in Phase 13, documented not fixed:**

1. **Answer-level numeric granularity** (§14). Any unsupported figure in a
   multi-sentence answer withholds the whole answer. Fail-closed but blunt.
2. **Contradictory definitions are not detected** (§9). Nothing compares two
   definitions of one term to each other.
3. **Abbreviations still end a sentence.** `_SENTENCE_BOUNDARY` fixes the
   numeric case; `Inc.` and `No.` still truncate a context.

**Carried forward and re-confirmed:**

4. **Anaphora is not resolved.** Where a pronoun is the only party identifier,
   the answer is withheld rather than a referent chosen — measured, not asserted
   (`ent_pronoun_referent_is_ambiguous`).
5. **Individuals** are identified only through an obligation verb they govern.
6. **Cross-clause reasoning** is not performed; a conclusion drawn from two
   clauses read together is unsupported.
7. **References are flagged, not resolved.** The system refuses to invent the
   content of Schedule 4; it does not go and read it.
8. **English only.** Every vocabulary is English, and the German-law and EU
   sources used here are English-language instruments.
9. **Sentence-level claim units.** A claim spanning a semicolon-joined clause
   is judged as one unit.
10. **Heuristic injection detection.** An instruction phrased as a provision,
    with a party as its subject, will not be caught by `looks_like_injection`.
11. **No browser test suite** (§12).
12. **Corpus size.** 211 cases across five real agreements and one regulation.
    Not a statistical sample of anything.
13. **No legal correctness claim.** The verifier establishes what a document
    says. It has no view on whether a clause is fair, enforceable or complete,
    and this product is not a lawyer.

---

## 17. Architecture Decision

**Named-entity handling: Option B — a constrained deterministic
representation.**

Rejected **Option A** (keep the limitation and fail closed): the limitation was
real, it fired on real contract text from two different SaaS agreements, and it
turned out to be cheap to close. Keeping it would have meant shipping a known
miss on the most common way contracts name their parties.

Rejected **Option C** (an NLP dependency): spaCy was never installed because the
measured benefit over the deterministic patterns was zero — the Phase 12
experiment already showed the deterministic approach at 12/12 with the parser
unavailable, and Phase 13's extractor reaches 15/15 and 3/3-on-real-text with
no dependency. The costs are not only the ~40 MB and the model download. A
parser is a second component with its own opinion about a sentence, and the
entire design rests on the verifier being the single deterministic authority.
Its statistical judgements would also make behaviour harder to explain to a
user, which is what this product sells.

Assessed against the brief's criteria:

| Criterion | Assessment |
|---|---|
| Detection performance | 15/15 synthetic, 3/3 on real named-entity cases, 12/12 role corpus |
| False-positive impact | 0 across all 211 cases; 4 caught and fixed during development |
| False-negative impact | 0 on measured constructions; anaphora and bare individuals remain |
| Test coverage | 31-case matrix + 10 unit assertions + 3 real-text cases |
| Implementation complexity | ~90 lines, one module, no new files in `app/` |
| Deployment cost | Zero — no dependency, no model, no download |
| Explainability | Every verdict names a rule a reader can check by eye |
| Security impact | Cannot promote a claim; all branches only withhold |

`experiments/role_binding.py` is retained so the comparison can be re-run if
the deterministic approach starts failing on real documents.

**No second LLM, no vector database, no additional agents were added.**

---

## 18. Final Test Results

```
$ cd backend && .venv/Scripts/python.exe -m pytest -p no:cacheprovider --durations=5
902 passed, 1 deselected, 6 warnings in 73.31s
```

| Measure | Baseline | Final | Δ |
|---|---|---|---|
| Passed | 697 | 902 | +205 |
| Failed | 0 | 0 | — |
| Errors | 0 | 0 | — |
| Skipped | 0 | 0 | — |
| Deselected (live) | 1 | 1 | — |
| Live network calls | 0 | 0 | — |
| Test files | 21 | 24 | +3 |
| Execution time | 18.96 s | 73.31 s | +54.35 s |

Frontend: build ✓ · `tsc -b` exit 0 · `oxlint` exit 0.

**Nothing was committed.** `git status` shows the working tree untracked, as at
the start of the phase. `.env` remains gitignored (`git check-ignore -v .env` →
`.gitignore:2`). No secret appears in any source, test, doc or report; the
`nvapi-…` strings in the test suite are canary values whose purpose is to
assert that keys do *not* leak.

---

## 19. Remaining Risks

1. **The central risk is unchanged and was reinforced, not reduced.** Phase 12
   reported 14/14 on FAR and that number did not predict 15/28 on other
   contract families. **Phase 13's 100% figures carry exactly the same
   weakness.** They say the verifier handles the cases we thought to write.
   Another family — insurance, construction, loan agreements, consumer terms —
   may well produce another 50% result.
2. **Adversarial cases are self-authored.** We transform real wording in the
   ways we anticipate. A transformation nobody here imagined is not measured.
3. **Vocabularies are closed sets.** Each has now been extended twice from real
   text, which is evidence they were incomplete, not that they are now complete.
4. **Two bugs sat undetected across three phases.** Both the substring matching
   and the decimal boundary silently disabled checks while tests passed. Other
   checks may be similarly inert without any test failing — a check that never
   fires looks exactly like a check that never needs to.
5. **The frontend is unverified in a browser.** No claim is made about what a
   user actually sees.
6. **No end-to-end validation with the real model.** Every figure here is the
   application's behaviour against hand-written claims.
7. **Multi-sentence pairing is more permissive** than comparing against the
   whole window. Guarded by a test, but it is a deliberate loosening.

---

## 20. Recommended Phase 14

In priority order.

1. **Adversarial corpus construction by someone who did not write the checks.**
   The single highest-value activity. Every corpus so far shares an author with
   the verifier, and Phase 13 shows how much that hides. Even one outside
   contributor writing attacks would be worth more than another thousand
   self-authored cases.
2. **Audit for inert checks.** Two silently-disabled checks in three phases is
   a pattern, not an accident. Add mutation-style coverage that asserts each
   semantic issue *can* fire on a crafted input, so a check that never fires
   fails the build.
3. **Align numeric and semantic granularity** (§14). Move numeric verification
   to the claim sentence, measure the false-positive and false-negative effect
   on all six corpora, and integrate only if neither worsens.
4. **Two more contract families**, ideally non-US and non-EU — Indian, Singapore
   or Australian commercial agreements — to test the same generalisation
   question again rather than assuming it is now settled.
5. **A minimal browser test suite.** Install one runner and cover the six states
   that carry safety meaning: withheld finding, partial verification,
   verification failure, Q&A not-found, provider failure, disclaimer
   visibility. Do not attempt full UI coverage.
6. **Live end-to-end validation**, budgeted and isolated: a handful of real
   Nemotron calls against known documents, measuring how often the model
   produces answers the gate must withhold.

**Not recommended:** a second LLM, a vector database, an agent framework, or an
NLP dependency. Phase 13 found its largest defects in two regexes; the returns
are still in measurement and in the deterministic layer, not in new
infrastructure.
