# PromptWars Legal AI — Architecture Decision Summary

## Frozen Decisions

| Area | Decision |
|---|---|
| Product | Evidence-grounded legal document intelligence |
| Primary model | NVIDIA Nemotron 3 Nano Omni 30B-A3B Reasoning |
| AI framework | LangChain |
| Workflow orchestration | LangGraph-style explicit state graph |
| Backend | FastAPI + Python |
| Frontend | React + Vite + TypeScript + Tailwind |
| PDF extraction | PyMuPDF initially |
| OCR | Model/native multimodal path first; fallback only if needed |
| Verification | Deterministic backend |
| Storage | Ephemeral by default |
| RAG | Not required for initial MVP |
| Vector DB | Not required for initial MVP |
| Fine-tuning | Not required |
| Multi-agent swarm | Not required |
| Model abstraction | Required |
| Evidence requirement | Required |
| Coverage gate | Required |
| Output gate | Required |
| Release boundary | Single, mandatory, structurally enforced (Phase 15) |
| OCR fallback | Not built — an unreadable page blocks analysis instead |
| DOCX | Not built — rejected at validation |
| Document comparison | Not built — see the scope decision below |
| Summaries / checklists / export | Not built — see the scope decision below |

## Why LangChain + LangGraph?

LangChain provides a practical abstraction for models, tools, structured outputs, and agent integrations.

LangGraph is appropriate for explicit stateful workflows when the application needs fine-grained control over transitions and failure states.

This project needs control more than autonomy.

## Why not pure autonomous agents?

Legal-document processing has strict invariants:
- all required pages must be processed,
- evidence must be traceable,
- unsupported claims must be blocked,
- failures must stop the workflow.

A deterministic workflow with agentic reasoning is therefore more appropriate than a free-form autonomous agent.

## Why Nemotron?

NVIDIA currently positions Nemotron 3 Nano Omni specifically for multimodal document intelligence and publishes strong document/multimodal benchmark results. The model has a current NVIDIA API endpoint, supports tool calling and JSON output, and lists a 256K context length.

These facts support the selection, but they are not proof of superiority for this exact legal use case. The application must still be evaluated on representative documents.

## Q&A decisions (Phase 9)

### Synchronous, unlike analysis

`/ask` answers in the response; `/analyze` hands back a job to poll. The two
differ because the work differs: an analysis reads a whole document and
produces many findings, and nobody watches it happen. A question produces one
short answer and a person is waiting for it, so a job id and a polling loop
would be worse for the user and no safer. `QA_TIMEOUT_SECONDS` (default 120)
bounds the held connection, below the analysis provider timeout.

Limitation, accepted: a proxy with a short idle timeout can cut the request
before the model answers. If that becomes real in deployment, the fix is to
move Q&A onto the existing analysis runner rather than to invent a second
execution model.

### A support status, not a confidence score

`supported` / `partially_supported` / `not_found` describe how well the
document backs the answer. No number is attached. The project has no calibrated
basis for a probability, and a figure like "87% confident" would imply one it
cannot defend — which is precisely the kind of unearned authority this product
exists to avoid.

### Still no RAG, no embeddings, no vector database

ADR-004 declined retrieval infrastructure for analysis. Q&A does not change the
calculus:

- The unit of work is still one document, which fits the model's context. The
  problem retrieval solves — choosing what to send — does not arise.
- Retrieval would add a failure mode that is invisible to the user and to the
  verifier: a chunk that was never retrieved produces a confident "not found"
  indistinguishable from a true one. Sending whole pages means a not-found
  answer means the model saw the document and still could not answer.
- Page identity is the spine of verification. Chunking would have to preserve
  it anyway, at which point the chunker is doing the paging the payload
  already does.

If documents grow past the context window, retrieval becomes necessary and the
coverage gate must then account for what was *retrieved* as well as what was
extracted. That is a design change, not a drop-in.

### No chat history

Each question is answered from the document alone. Carrying earlier turns would
introduce a second source of context that the verifier cannot check, so a model
could ground an answer in its own previous output rather than in the document.

## Phase 10: why there is no second LLM verifier

The obvious response to the semantic gap was to add a model that judges whether
an answer follows from its evidence. It was not added, for reasons measured
rather than assumed.

**The failure modes turned out to be deterministic.** The four classes that
escaped Phase 9 - polarity, modality, actor and conditionality - each turn on a
small closed vocabulary, not on open-ended meaning. A word list and a
content-overlap test close all four. The evaluation corpus now withholds 15/15
attacks while releasing 9/9 legitimate answers; a model-based judge would have
to beat that to earn its place.

**A second model would weaken the guarantee it appears to strengthen.** The
system's claim is that a deterministic, inspectable rule decides what reaches
the user. Replacing part of that with a second fallible judge means two
fallible judgements on the same question and no way to audit either. The
existing check chain can be read, reasoned about and unit-tested; an LLM's
verdict cannot.

**Cost and latency.** Q&A already holds a synchronous connection for tens of
seconds. A verification call would roughly double that, and double the metered
spend, for every question.

This decision is revisitable, and the conditions are explicit. A second model
becomes justified if a test corpus demonstrates a class of unsupported claim
that (a) occurs in practice, (b) resists deterministic checking, and (c) the
model-based judge actually catches. If it is ever added it must run *after* the
deterministic checks, must only be able to lower a verdict, and must fail
closed on error - never override an evidence check, never promote a claim.

The same reasoning continues to exclude multi-agent verification, a vector
database and RAG: none addresses a failure this project has measured, and each
adds an unauditable step between the document and the answer. See also ADR-004
and the Phase 9 note on retrieval above.

## Phase 11: what the expanded corpus changed

Phase 10 reported 15/15 and 9/9 on a 24-case corpus and concluded the semantic
gap was "closed". That was wrong, and the way it was wrong is worth recording:
**a corpus on which everything passes has not been made hard enough.** The
checks had been developed against those cases, so the corpus measured whether
the implementation matched its own fixtures.

Widening it to 67 cases - more paraphrases, more sentence shapes, more legal
vocabulary, plus categories nothing was known to handle - produced a **35.1%
false-negative rate** and two false positives. Both false positives were
legitimate clauses destroyed by the injection blacklist: "the consultant may
act as the company's agent" and "the parties shall treat this as confidential".

Three conclusions were carried forward.

**A blacklist alone is both too narrow and too broad.** Too narrow because an
attacker picks different words; too broad because legal drafting is built from
imperatives. Detection now combines a list of phrases with no contractual use
and a structural test: a real provision has a party as its subject, an injected
instruction commands the reader and binds nobody. Both signals are needed, and
the boundary is tested from both sides - 8 malicious strings that must be
caught, 12 legitimate clauses that must not be.

**The overlap threshold is not a safety parameter.** A sweep from 0.4 to 0.8
moved exactly one case in the corpus, and it moved it between "withhold the
whole answer" and "release the evidenced sentence, drop the other". At no value
does an unsupported claim reach the user. 0.6 is retained as the more
conservative side of a usefulness trade-off, not because safety turns on it.

**Some gaps are architectural, not lexical.** Role reversal between two named
parties resists every vocabulary check, because both parties are present in the
evidence and only their grammatical roles differ. It is left open and
documented rather than approximated - a word-order heuristic would be fragile
and would introduce false positives in exactly the passive constructions legal
text is full of.

The rates after these changes (8.1% false negative, 0% false positive) are
**not independent validation**: the new checks were developed against the
corpus that measures them. What the corpus is good for is regression - it is
wired into the test suite, and cases in unsupported categories assert that they
*still fail*, so the limitation list cannot silently go stale.

## Phase 12: real contract text, and the role-binding decision

Two questions, both answered with measurements.

### Do the checks generalise beyond their own fixtures?

Partly. A corpus of verbatim FAR clauses - real federal contract language, no
part of it written here - found **three failures the synthetic corpus never
did**, and every one was a vocabulary gap rather than a design flaw:

- "reserves the right to" grants a permission. The modality vocabulary did not
  contain it, so a correct answer about FAR 52.212-4(l) was withheld.
- "for its sole convenience" restricts a right. "solely" was in the vocabulary,
  "sole" was not, so broadening it to "for any reason" went undetected.
- A long clause ending "and without its fault or negligence" made every shorter
  answer look like a dropped negation, because the polarity check did not ask
  whether the claim restated the negated part.

That last one is the most interesting: it was not a missing word but a missing
*locality* rule. A negation reverses meaning only if the claim says the rest of
its phrase. The fix generalises; the other two were vocabulary.

The lesson for later phases is that vocabulary written alongside the checks
will keep being incomplete, and only unfamiliar text finds the holes.

### Is a dependency parser justified?

**No.** Measured, not assumed.

| Approach | Reversals detected | Legitimate preserved | Cost |
|---|---|---|---|
| Party presence (shipped) | 3/12 | 8/8 | none |
| Deterministic role binding | 12/12 | 8/8 | 0.1 ms / 20 cases, no dependency |
| spaCy dependency parse | not installed | - | ~40 MB + model |

Two surface patterns - the agent after "by" in a passive clause, otherwise the
first party named - closed the gap entirely on the role corpus, including the
active/passive paraphrases that defeat a naive word-order rule and the
single-party clauses where a role checker must stay silent. A parser was never
installed, because there was nothing left for it to improve.

The deterministic version was then validated against 93 cases from corpora it
was not designed for, producing zero new false positives, before being
integrated.

**Decision: Option A** on the dependency question - keep the project free of an
NLP dependency - with the deterministic role binding integrated instead.
`backend/experiments/role_binding.py` is retained so the comparison can be
re-run if the vocabulary approach starts failing on real documents.

## Phase 13 - named entities, and whether to add an NLP dependency

The Phase 12 decision above was taken on a corpus where every party was a role
noun. Phase 13 re-opened it against real agreements, where parties are named
companies: Anthem/Castlight, Demandware/neckermann.de, Albemarle, Becknell.

### What the measurement said

Reproducing the failure first (`backend/experiments/role_binding.py` and the
Phase 13 baseline) showed the Phase 12 diagnosis was wrong. Phase 12 concluded
that named-entity binding needed capitalisation, which the casefolded evidence
context destroys. It does not: the subject slot of an obligation verb is
decidable in lower case, and that is where a contract puts the party it binds.

| Approach | Named-entity reversals | False positives | Cost |
|---|---|---|---|
| Phase 12 shipped behaviour | 0 / 3 on real SaaS text | 0 | - |
| Subject-slot extraction (`named_parties`) | 3 / 3 on real SaaS text, 15 / 15 on the entity matrix | 0 across 6 corpora | ~90 lines, no dependency |
| spaCy dependency parse | not installed | - | ~40 MB + model, and a second thing that can disagree with the verifier |

### Decision: Option B - a constrained deterministic representation

Not Option A (keep the limitation): the limitation was real, it fired on real
contract text, and it turned out to be cheap to close.

Not Option C (an NLP library): a parser was never installed because the
measured benefit over the deterministic patterns was zero, and the costs are
not only megabytes. A parser is a second component with its own view of a
sentence, and the project's whole design rests on the verifier being the single
deterministic authority. Its statistical judgements would also make the
verifier's behaviour harder to explain to a user - the thing this product sells.

The rule stays narrow on purpose. It reads a closed set of verbs, refuses runs
headed by a document noun or a role noun, and skips passive subjects. Where it
cannot identify an actor it returns nothing and the presence check applies, as
before. Nothing here can promote a claim; every branch can only withhold.

### What this decision does not cover

Anaphora and individuals named without an honorific or a governing verb. Each
is measured and recorded rather than asserted - see the Phase 13 report and
`docs/04_SECURITY_GROUNDING.md`. (Contradictory definitions were on this list
until Phase 14 closed them; see below.)

## Phase 14: one verification layer, two surfaces

**Decision: the analysis path calls the Q&A path's own checks, not a copy.**

Phase 14 found that claim-level semantic verification had never run on the
analysis findings endpoint. A finding whose claim reversed its own quote was
returned as `verified`. Three ways to fix it were available:

- **A. Duplicate the checks in the analysis node.** Rejected outright. Two
  implementations of one rule drift, and the drift is silent - which is
  precisely the failure being fixed.
- **B. Move verification into the output gate for both paths.** Rejected as
  too large for the phase that discovered the bug. The gate would have to know
  about evidence contexts, which is verification's business, not routing's.
- **C. A thin module that composes the existing functions.** Chosen.
  `verify_analysis_claims` calls `verify_analysis`, then the same
  `check_answer`, `looks_like_injection`, `quotes_reported_speech` and
  `conflicting_definitions` the Q&A gate calls. It invents no rule and owns no
  vocabulary.

The audit that found this is kept as a test (`test_inert_check_audit.py`) with
a **production path** and **outcome affects gate** column for every dimension,
asserted by substitution rather than by reading the code. A check that stops
being called now fails a test.

### Two checks measured and rejected

Both caught a real attack in the independent corpus and both were reverted:

| Check | Caught | Cost | Verdict |
|---|---|---|---|
| Subject-qualifier dropping | "Invoices *disputed in good faith*" → "Invoices" | 4 correct answers withheld on real FAR and employment text | Reverted |
| Enumerated-exclusion truncation | "war, nuclear risk, *or wilful misconduct*" → "war or nuclear risk" | 6 correct answers withheld on real FAR, SaaS, employment and DPA text | Reverted |

The principle they were measured against: a verifier that eats real provisions
is not safer, only less useful. Both are recorded as comments at the point in
`semantics.py` where they would have gone, with the measurement, so the next
person does not rediscover them as a good idea.

### Numeric granularity

Phase 13 recorded the whole-answer/per-sentence mismatch as blunt but safe.
Phase 14 found the other direction is unsafe: values compared against the whole
page let a figure from one clause be asserted about another. The decision was
to **add** per-claim value binding beneath the existing answer-level check
rather than replace it - neither is relaxed, both must pass, and the change can
only withhold more.

## Phase 15: one release boundary, and one refusal

**Decision: a single output policy owns what reaches a user.**

Phase 14 fixed a path. Phase 15 found the same class of gap in the payload -
`section`, `explanation`, `attention` and `type` all reached a response
unverified - and concluded that adding a fifth check would repeat the mistake.
`app/verification/policy.py` is the place where "may this reach a user" is
decided, and `build_result` may render only what it produced.

The structural half matters as much as the checks: `output_gate_node` makes the
decision and stores it, so a run that skips the boundary publishes nothing.
`test_structural_safety.py` asserts this by substitution rather than by
inspection - replace a control and the endpoint's response must change.

**Decision: `attention` is derived, not received.** A risk level chosen by the
model is a risk level chosen by the thing the application exists to check. It
is now computed from the verified evidence by counting features the text
contains, and the schema says plainly that it is not a legal risk assessment.

**Refused: contradiction gating on explanations.** Four variants were
implemented and measured against 28 explanations written for the purpose:

| Rule | False positives | Attacks missed |
|---|---|---|
| contradiction vs evidence | 2 / 20 | 5 / 8 |
| contradiction vs the verified claim | 2 / 20 | 5 / 8 |
| reversal axes, overlap >= 0.6 | 3 / 20 | 3 / 8 |
| reversal axes, overlap >= 0.8 | 1 / 20 | 6 / 8 |
| values must be in the evidence (shipped) | 0 / 20 | 7 / 8 |

The semantic axes are calibrated for one-sentence restatements; an explanation
is paraphrase-heavy prose across several sentences, and against it they are
wrong in both directions at once. Shipping any variant would withhold correct
findings *and* leave most reversed explanations in place. What shipped is the
part that works - values bound to evidence, at zero measured cost - plus a
label in the UI. That is weaker than verification, and the report says so
rather than implying the field is checked.

## Phase 23: two providers, one authority

**Decision: provider roles, not a provider.** Analysis (`ANALYSIS_PROVIDER`),
Q&A (`QA_PROVIDER`) and reasoning notes (`REASONING_PROVIDER` +
`REASONING_ENABLED`) are configured separately. Gemini is the default for the
first two, Nemotron for the third. Either switch saying "off" disables
reasoning, so no combination is contradictory.

**Decision: no fallback, silent or otherwise.** A role whose key is missing
reports `not configured`; it never calls a different vendor. Two providers
produce different findings from the same document, and a result whose provider
changed without anyone knowing cannot be audited or reproduced. Provenance
records the provider actually called.

**Decision: reasoning runs after the release gate, over released findings
only.** A second model is useful for pointing out that two clauses should be
read together; it is not an authority on either. So it never sees page text or
withheld proposals, its notes are gated for scope (known ids, quotes from the
cited findings, figures present in them, no instructions, no legal
conclusions), and every note carries a fixed "not independently verified" label.
It cannot change a finding — asserted by deep-equality tests under hostile
output. This is *not* the rejected "second LLM verifier": nothing it produces
decides a release.

**Decision: translations are additions, never replacements.** The semantic
checks read English. A Tamil claim, explanation or answer would pass through
checks that cannot read it, so checked text stays in the document's language
and a translation is released *beside* it — only when the original fully
passed, only when every numeral in it appears in the evidence, and always
labelled "not independently checked". This is stricter than the plan approved
for Phase 23, which would have released a Tamil explanation in place of the
checked one.

**Decision (ADR-005 amendment): optional metadata persistence.** Supabase may
store document metadata, analysis-job metadata, *released* findings and Q&A
metadata. Never stored: PDFs, page text, the raw filename (a salted SHA-256
and the extension instead), questions, answers, withheld or unverified output,
reasoning-note text, prompts, keys. Backend-only with the service-role key; RLS
on every table with no policies, so browser roles can do nothing; writes refused
unless the migration's schema probe answers. Rows cascade-delete on discard, on
TTL expiry and on retention. The metadata is **not anonymous** — it is linked by
document id — and there is no authentication, so there is no per-user
isolation: acceptable for a single-tenant demo, a blocker for public use.

**Decision: the pre-Phase-23 suite runs unchanged.** `conftest.py` pins the
roles it was written against (Nemotron, no reasoning, no persistence) and blanks
every key. The product defaults are tested separately. One pre-existing test
changed: an exact response-key set was extended by the three approved fields,
and remains exact.

## Scope: depth over breadth, against the problem statement

**Decision: cover fewer of the problem statement's suggested directions, and
verify what is covered.**

The PromptWars problem statement — *AI for Legal Assistance & Access* — lists
seven potential use cases and states explicitly that they are directions rather
than a specification: not exhaustive, not prescriptive, and participants are
encouraged to develop different ones.

This project implemented two of them (document-grounded Q&A; clause and
obligation highlighting, with plain-language claims) and deliberately did not
implement the others — comparison, summaries, checklists, next-steps guidance,
and preparation packs for a lawyer. The reason is uniform across all five:

> Each is a claim the verifier cannot bind to one evidence sentence.

A summary spans a document; a comparison spans two; a next step is a
recommendation about the world rather than a statement about the text. The
verification layer this project is built on binds a claim to the sentence its
evidence sits in, and Phases 10–15 are the record of how much work that
binding took for the simple case. Shipping the harder cases *unverified* would
contradict the one property the product exists to demonstrate, and shipping
them verified is not a feature — it is another research phase.

**Decision: the three unresolved corpus cases stay unresolved.** Two phases
have now written, measured and reverted lexical fixes for them. The general
result is in `PHASE_15_REPORT.md` §7: no word-level rule separates dropping a
restrictive phrase from summarising, and paraphrase into plain language is what
this product is for. A third attempt of the same kind will fail the same way.

**Decision: the documentation states non-implementation explicitly.** Alignment
is claimed in exactly one place, `docs/11_PROMPTWARS_ALIGNMENT.md`, with status
labels that distinguish implemented, partially implemented, not implemented and
explicitly excluded. Inflating alignment would misrepresent a project whose
entire argument is that unverified claims should not be presented as verified.

## Final Principle

```text
LLM = interpreter/reasoner
Application = controller
Verifier = evidence authority
Output gate = safety boundary
```
