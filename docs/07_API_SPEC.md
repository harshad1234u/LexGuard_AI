# PromptWars Legal AI — API Specification

**Status:** as-built, current as of Phase 15. Every endpoint below exists.

There is no summary endpoint, no comparison endpoint, no checklist endpoint and
no export or download endpoint — the surface inventory in `PHASE_15_REPORT.md`
§2 confirms their absence, and `docs/11_PROMPTWARS_ALIGNMENT.md` explains why.

## Base

```text
/api/v1
```

## Errors

Every failure returns the same envelope with a stable machine-readable `code`,
so a client can render a specific state rather than a generic failure:

```json
{
  "error": {
    "code": "coverage_incomplete",
    "message": "Some pages could not be processed.",
    "details": {}
  }
}
```

`message` is plain language, safe to display. Responses never carry stack
traces, provider exception text, prompts, API keys or internal paths.

## Document lifecycle

Two resources, each owning one half of the journey, so no state is tracked in
two places:

- The **document** resource owns validation and extraction. Its `status` is
  one of `validated`, `extracting`, `ingested`, `ingestion_failed`.
- The **analysis** resource owns everything from the coverage gate onward. Its
  `status` and `stage` are described under the analysis endpoints below.

`DocumentStatus` in the schema also declares the later states of the workflow
machine in `docs/02_ARCHITECTURE.md` §4 (`analyzing`, `ready`, and so on).
Those are **not** produced by the document endpoints: from Phase 7 that part of
the machine is realized by the analysis resource. `test_end_to_end.py` pins the
set the document endpoints can actually return.

## POST /documents/upload

Upload a PDF as multipart form data under the field name `file`.
Validates extension, MIME type, file signature, size, page count and
parseability before the document is stored. **201 Created** on success.

Response:

```json
{
  "document_id": "doc_123",
  "filename": "contract.pdf",
  "page_count": 50,
  "size_bytes": 482913,
  "content_type": "application/pdf",
  "status": "validated",
  "source_repaired": false
}
```

`source_repaired` is true when the PDF had to be structurally repaired to be
read at all. Such a document is never eligible for a complete-document
analysis, because its page count is itself reconstructed.

Failure codes: `empty_file`, `file_too_large` (413), `unsupported_extension`,
`unsupported_mime_type`, `signature_mismatch`, `corrupt_document`,
`encrypted_document`, `no_pages`, `too_many_pages`, `unsafe_filename`.

## POST /documents/{document_id}/extract

Run page-level extraction and return the per-page manifest with the coverage
verdict. Deterministic and entirely local — no model is involved. Safe to call
more than once; a re-run replaces the previous result.

Response:

```json
{
  "document_id": "doc_123",
  "status": "ingested",
  "manifest": {
    "document_id": "doc_123",
    "total_pages": 50,
    "is_repaired": false,
    "extraction_method": "pymupdf_text",
    "pages": [
      {
        "page_number": 1,
        "status": "processed",
        "text_length": 2417,
        "image_count": 0,
        "failure_reason": null
      }
    ]
  },
  "coverage": {
    "status": "complete",
    "expected_pages": 50,
    "processed_pages": 50,
    "failed_pages": [],
    "unreadable_pages": [],
    "blocking_reasons": []
  }
}
```

Page status is one of `processed`, `empty`, `unreadable`, `failed`. A blank
page counts as processed — there was no content to miss. An `unreadable` page
carries images but no text layer (almost always a scan), and its content was
*not* captured, so it blocks a complete-document analysis.

## GET /documents/{document_id}/manifest

The per-page processing record on its own. **409** until extraction has run.

## POST /documents/{document_id}/analyze

Starts controlled analysis.

Asynchronous as of Phase 7: a real model call takes tens of seconds, so the
request must not stay open for it. Returns **202 Accepted** while work is
outstanding, or **200 OK** when an already-completed analysis is handed back.

Response:

```json
{
  "analysis_id": "an_4f1c2d9e0b",
  "document_id": "doc_123",
  "status": "queued",
  "stage": "queued",
  "created_at": "2026-01-01T09:00:00Z",
  "reused": false
}
```

Repeating the request while an analysis is queued, running or completed returns
that same analysis with `reused: true` rather than starting a second one. A
*failed* analysis starts a new run. There are no automatic retries.

## GET /analysis/{analysis_id}/status

Poll while an analysis runs. Safe metadata only — no prompts, no raw model
output, no document text, no provider or stack detail.

Response:

```json
{
  "analysis_id": "an_4f1c2d9e0b",
  "document_id": "doc_123",
  "status": "running",
  "stage": "analyzing",
  "created_at": "2026-01-01T09:00:00Z",
  "started_at": "2026-01-01T09:00:00Z",
  "completed_at": null,
  "duration_ms": null,
  "coverage": {
    "status": "complete",
    "expected_pages": 50,
    "processed_pages": 50,
    "failed_pages": [],
    "unreadable_pages": [],
    "source_repaired": false
  },
  "proposed_count": null,
  "verified_count": null,
  "withheld_count": null,
  "error_category": null,
  "error_message": null
}
```

`status` is one of `queued`, `running`, `completed`, `failed`. `completed` is
set only once the output gate has run; a workflow that stopped earlier is
`failed`, whatever the reason.

`stage` names the workflow step, one per graph node: `queued`, `validating`,
`ingesting`, `checking_coverage`, `building_document_map`, `analyzing`,
`verifying`, `gating_output`, `done`.

On failure, `error_category` is one of `validation_error`, `ingestion_error`,
`coverage_error`, `provider_not_configured`, `provider_unavailable`,
`provider_timeout`, `provider_rate_limited`, `model_output_invalid`,
`verification_error`, `analysis_timeout`, `internal_error`, and
`error_message` is plain language safe to display.

## GET /documents/{document_id}/values

A deterministic index of the values the document contains. **No model is
involved**, so this endpoint works while the provider is unavailable.

It reports what the document *says*, never what it means. A value here is a
string that occurs in the document and the page it occurs on — not a deadline,
an obligation or a risk. Establishing that a figure is an obligation is
interpretation, and interpretation belongs to `/findings`, where a model
proposes it and the verifier checks it.

**409** `coverage_incomplete` until every page has been read — the same gate
`/analyze` uses. An index built from a partially captured document would
under-report silently, and a reader cannot tell an absent value from an unread
page.

Response:

```json
{
  "document_id": "doc_123",
  "coverage_status": "complete",
  "values": [
    { "kind": "duration",   "value": "30 days",      "page": 2, "ambiguous": false },
    { "kind": "currency",   "value": "Rs 50,000",    "page": 2, "ambiguous": false },
    { "kind": "percentage", "value": "1.5%",         "page": 2, "ambiguous": false },
    { "kind": "date",       "value": "1 April 2026", "page": 1, "ambiguous": false }
  ]
}
```

`kind` is one of `currency`, `percentage`, `duration`, `date`. Bare integers
and decimals are deliberately excluded: an unqualified figure carries no unit
and would bury the values that do.

`value` is the document's own spelling, recovered from the page so the index
does not misquote. It is never paraphrased and never reformatted.

`ambiguous` applies to dates only. A written form with more than one reading —
`04/05/2026` — is reported as written with `ambiguous: true`, and no calendar
meaning is assigned.

Values are **deduplicated within a page** and never across pages: the same
period on page 2 and page 5 is two facts about two places.

**No surrounding prose is returned.** A value carries only its kind, its text
and its page. This keeps the endpoint an extraction surface rather than a claim
surface, and minimises document-text exposure.

Failure codes: `document_not_found` (404), `coverage_incomplete` (409).

## GET /documents/{document_id}/status

The application's own record of what was read, so a client never has to take
completeness on trust.

Response:

```json
{
  "document_id": "doc_123",
  "status": "ingested",
  "expected_pages": 50,
  "processed_pages": 50,
  "failed_pages": [],
  "unreadable_pages": [],
  "coverage_status": "complete",
  "coverage_explanation": "Every page of this document was processed.",
  "analysis_eligible": true,
  "source_repaired": false
}
```

`coverage_status` is one of `pending`, `processing`, `complete`, `incomplete`,
`failed`, `blocked_repaired`. **`analysis_eligible` is the field a client acts
on** — it is true only for `complete`, and it is the coverage controller's
verdict, never the model's. The backend enforces the same rule independently:
a client that ignores this field and posts to `/analyze` anyway gets a
terminal analysis with `error_category: "coverage_error"`, and no model call
is made.

`coverage_explanation` is plain language written for a non-technical reader
and is suitable for display as-is.

## DELETE /documents/{document_id}

Discard a document and any analysis of it immediately, rather than waiting for
the TTL. **204 No Content**. Afterwards the document, its status and its
analysis all return 404.

## GET /documents/{document_id}/findings

The gated result. **409** until an analysis has completed; **404** if none has
been run.

`result.findings` contains only findings that passed the output gate — those
whose `verification_status` is `verified`. Everything the model proposed that
did not survive verification appears as counts in `result.withheld`, never as
content.

Response:

```json
{
  "document_id": "doc_123",
  "analysis_id": "an_4f1c2d9e0b",
  "status": "completed",
  "result": {
    "findings": [
      {
        "id": "f_001",
        "type": "termination",
        "claim": "Either party may terminate with 30 days written notice.",
        "evidence": {
          "page": 37,
          "section": "Termination",
          "quote": "30 days' written notice"
        },
        "explanation": "Either side can end the agreement with a month's notice.",
        "explanation_verified": false,
        "attention": "review",
        "verification_status": "verified"
      }
    ],
    "withheld": {
      "total": 1,
      "rejected": 1,
      "unverified": 0,
      "partially_verified": 0
    },
    "proposed_count": 2,
    "insufficient_evidence": false,
    "coverage": {
      "status": "complete",
      "expected_pages": 50,
      "processed_pages": 50,
      "failed_pages": [],
      "unreadable_pages": [],
      "source_repaired": false
    }
  },
  "overview": { "…": "see below" }
}
```

`insufficient_evidence` is true when the model proposed findings and none
survived verification.

### What each field of a finding is, and who decided it

Everything in this response comes from the release policy
(`app/verification/policy.py`), which is the single boundary every published
field passes through. A run that did not reach that boundary returns no
findings rather than the model's proposal.

| Field | Decided by |
|---|---|
| `claim` | Model-proposed, then verified against its own evidence claim by claim. Withheld entirely if contradicted. |
| `evidence.quote` | Model-proposed, located in the document by the verifier. |
| `evidence.page` | Model-proposed, confirmed to exist and to contain the quote. |
| `evidence.section` | Model-proposed, then **confirmed by whole-label containment against the cited page, or dropped**. A citation that cannot be confirmed is never shown — it is the part a reader cannot check without the document in front of them. |
| `explanation` | Model-proposed. Released only when it does not change a figure and does not read as an instruction. **Not verified.** |
| `explanation_verified` | Application. `false` — the normal case — means the sentence is interpretation, and **a client must not present it as a verified fact about the document**. The reference UI labels it *"Interpretation — not verified against the document"*. |
| `attention` | **Derived by the application** from features the verified quote demonstrably contains: a prohibition, an obligation, a sum, a deadline, consequence vocabulary. Never the model's choice, and **not a legal risk assessment** — it says nothing about whether a clause is onerous, unusual, unenforceable or unfair. **The reference frontend does not render this field** (see below). |
| `type` | Model-proposed, length-bounded, and refused if it reads as an instruction. |
| `verification_status` | The application's deterministic verdict. Only `verified` appears in `findings`. |

Nothing the model asserts about its own output — a verification flag, a
confidence score, a risk level — influences any of this. Such fields are
dropped at parse and are unreadable thereafter.

**What the reference frontend renders.** A client is free to use every field
above, but the frontend in this repository does not use all of them: it renders
the claim, quote, page, confirmed citation, explanation (labelled when
`explanation_verified` is false) and the withheld counts. It does **not**
render `attention` — the field is present in its TypeScript types but no
component displays it, and there is no attention badge or severity indicator in
the interface. Documentation describing this API must therefore not present
`attention` as a user-facing risk indicator.

### `overview` — the same findings, grouped

The response also carries an `overview`: `result.findings` arranged under a
closed list of document topics. It is **additive and derived**. Every claim,
quote, page and citation in it is already present in `result.findings`, so a
client that ignores the field loses no information — and one that uses it
gains no content the output gate did not already publish.

```json
{
  "overview": {
    "categories": [
      {
        "key": "termination",
        "label": "Termination",
        "items": [
          {
            "finding_id": "f_001",
            "claim": "Either party may terminate with 30 days written notice.",
            "quote": "30 days' written notice",
            "page": 37,
            "section": "Termination",
            "label": "termination"
          }
        ],
        "empty_message": null
      },
      {
        "key": "liability",
        "label": "Liability",
        "items": [],
        "empty_message": "No verified finding was released for this category."
      }
    ],
    "released_count": 1,
    "proposed_count": 2,
    "withheld_count": 1
  }
}
```

`key` is one of a closed set: `parties_roles`, `term_renewal`, `fees_payments`,
`termination`, `confidentiality`, `liability`, `notices`, `governing_law`,
`other`. The model does not choose it. It proposes a finding's free-form
`type`, and the application maps that onto one of these by whole-word lookup
against a closed vocabulary; anything unrecognised becomes `other` and keeps
its own `label`. There is no code path from a model-supplied string to a
published heading.

The eight named topics are always present, empty or not. `other` appears only
when something is in it.

**What this is not.** It is not a summary — it contains no sentence about the
document as a whole, because a summary is a claim spanning a document and the
verifier binds a claim to the sentence its evidence sits in. It is not a
completeness check, a compliance verdict, or an assessment of any kind.

**`empty_message` reports the analysis, not the document.** An empty topic
means no finding about it survived verification. It does **not** mean the
document lacks such a clause — the application knows what it confirmed, not
what the document contains, and cannot establish the absence of a provision. A
client must not render an empty topic as missing, absent, incomplete or
non-compliant. The `released_count` / `proposed_count` / `withheld_count`
triple is published alongside so a reader can see the difference between "the
document is silent" and "this analysis released nothing here".

`explanation` and `attention` are deliberately **absent** from an overview
item. The explanation is interpretation and carries its own label on the
finding itself; repeating it inside a panel of verified content would blur that
distinction. `attention` is not a risk assessment and is not rendered as one.

The projection runs after the release boundary, in the route, and calls no
model — reading this endpoint repeatedly costs no inference.

## POST /documents/{document_id}/ask

Answer a question using only the uploaded document.

**Synchronous.** A question produces one short answer and a person is waiting
for it, so there is no job id and nothing to poll. The cost is that the request
holds a connection while the model reads; `QA_TIMEOUT_SECONDS` (default 120)
bounds it, below the analysis provider timeout. A client should expect this
call to take tens of seconds and must not retry it automatically.

The document must be eligible for a complete-document answer — the same
`require_complete_coverage` gate that governs `/analyze`. The model is not
called when the gate refuses.

Request:

```json
{
  "question": "What is the termination notice period?"
}
```

`question` is required, 1–2000 characters, and must not be only whitespace.
It is treated as untrusted input: it cannot redirect the model to another
document, and instructions inside it are data, not commands.

Response (**200**):

```json
{
  "document_id": "doc_123",
  "question": "What is the termination notice period?",
  "answer": "Either party may terminate with 30 days' written notice.",
  "status": "supported",
  "evidence": [
    {
      "quote": "30 days' written notice",
      "page": 37,
      "section": "Termination",
      "verification_status": "verified",
      "note": ""
    }
  ],
  "withheld_evidence": 0,
  "claims_checked": 1,
  "claims_withheld": 0,
  "disclaimer": "This is legal information drawn from your uploaded document, not legal advice. ..."
}
```

### Status values

| `status` | Meaning |
|---|---|
| `supported` | At least one quote verified, and none was contradicted. |
| `partially_supported` | Some support held up and some did not. Read the evidence. |
| `not_found` | Nothing could be confirmed. The model's own words are withheld. |

These are **support levels, not confidence scores**. The project has no
calibrated basis for a probability and does not imply one.

`verification_status` on each evidence item is the application's deterministic
verdict (`verified`, `partially_verified`, `unverified`, `rejected`), never the
model's claim about itself. Only `verified` and `partially_verified` quotes are
returned; `rejected` and `unverified` ones are counted in `withheld_evidence`
and their text is never sent.

### Claim-level grounding

The answer is split into sentences and each is checked against the sentence its
evidence sits in, on eight axes over closed vocabularies:

| Axis | Caught |
|---|---|
| Polarity | a dropped or added negation, including prohibition phrased without "not" |
| Modality | permission vs obligation vs prohibition (`may` → `must`) |
| Actor | a party absent from the evidence, and role reversal between vocabulary parties or named companies |
| Conditions | a conditional right presented as an absolute one |
| Certainty | an option restated as automatic ("may be renewed" → "will automatically renew") |
| Scope | a restriction dropped or broadened ("some services" → "all services") |
| Temporal direction | "before termination" → "after termination" |
| Time limits | a date or period restated as open-ended |

Alongside these, evidence is refused when it is text addressed to the
assistant, when it merely *points* to a definition or schedule rather than
stating its contents, when it records reported speech rather than a term of the
agreement, or when the document defines the same term twice and differently.

A sentence the evidence does not establish is removed from the answer and
counted in `claims_withheld`; its text is never returned.

`claims_checked` is how many statements the answer made. **A verified quote
does not make every sentence beside it verified** — that is what this layer
exists to prevent.

A polarity or modality difference in a sentence that otherwise restates the
evidence is treated as a contradiction, and the whole answer is withheld.

Causation, cross-clause reasoning, anaphora and definitional substitution are
*not* checked; claims resting on them are treated as unsupported rather than
guessed at. Scope and temporal reach are checked only over the vocabularies
above. The full list of what is not checked, and why, is in
`docs/04_SECURITY_GROUNDING.md` §7b.

`evidence[].section` is confirmed against the cited page by the same
`confirm_section` the findings path uses, or dropped — the two surfaces share
one implementation so they cannot drift apart.

### Request size

A JSON body larger than `MAX_JSON_BODY_BYTES` (default 64 KiB) is refused with
**413** `file_too_large` before it is parsed, so an oversized payload cannot be
decoded in full just to fail a 2000-character field limit. Multipart uploads
are unaffected and keep their own streaming limit.

A **chunked** request declares no length, so the pre-parse check has nothing to
test and the body is decoded in full. It is still refused — the 2000-character
field limit rejects it at the schema layer, and no oversized body reaches the
model — but the cheap early exit is lost. Verified by test. Closing it properly
needs a streaming read or a body limit in the reverse proxy.

### What the gate guarantees

The model's answer text reaches a client **only** when at least one of its
quotes verified against this document. If nothing verified, `answer` is the
application's own not-found text:

> I couldn't find this information in the uploaded document. That does not mean
> the document is silent on it — only that nothing could be confirmed, so
> nothing is shown.

That wording is deliberate. The system is not in a position to conclude that a
clause does not exist, only that it could not confirm one.

### Errors

| Status | Code | Cause |
|---|---|---|
| 404 | `document_not_found` | Unknown or expired document. |
| 409 | `coverage_incomplete` | Document not eligible — unreadable page, failed extraction, repaired PDF. The model is not called. |
| 422 | `invalid_request` | Missing, empty, whitespace-only, over-long or non-string question; malformed JSON. |
| 413 | `file_too_large` | JSON body over `MAX_JSON_BODY_BYTES`. Refused before parsing. |
| 429 | `model_rate_limited` | Provider rate limit. |
| 502 | `model_invalid_response` | Model returned something unusable. |
| 503 | `model_unavailable` / `model_not_configured` | Provider unreachable, or no server-side key. |
| 504 | `model_timeout` | Provider exceeded `QA_TIMEOUT_SECONDS`. |

Coverage refusal and provider failure are HTTP errors carrying the standard
error envelope rather than `status` values, matching the convention used
everywhere else in this API.

**The `message` on a provider failure is worded for the question, not for the
analysis.** Both features call the same provider through the same abstraction,
so `/analyze` and `/ask` return the same `code`, the same HTTP status and the
same `details.reason` for a given failure - but a reader of `/ask` is told the
question could not be answered, never that the analysis service failed. The two
run independently: a question can fail while a completed analysis stands, and
reporting one as the other told users their results had been withdrawn when
they had not. A client should switch on `code`, which is stable across both
paths, and display `message`, which is not.

| Failure | `/analyze` message | `/ask` message |
|---|---|---|
| `model_unavailable` | The analysis service is temporarily unavailable. | The question service is temporarily unavailable. No answer was generated or shown. You can ask again later. |
| `model_timeout` | The analysis took too long to complete. Please try again. | The question took too long to answer and was stopped. No answer was shown, because none could be checked against your document in time. |

`not_found` is **not** in this table and never becomes one of these. It is a
200 carrying an answer shape: the model completed the request and nothing it
proposed survived verification. A provider failure is a 5xx carrying no answer
at all. Collapsing the two in either direction would state that a document is
silent on something when the service simply never asked.

### Security

- The NVIDIA key is server-side only and never appears in a response or a log.
- Logs record document id, page count, question **length**, and counts — never
  the question, the answer, a quote, or document text.
- Only the asked-about document's pages are built into the model payload, so a
  quote can only ever be matched against that document.
- No chat history is kept; each question is answered from the document alone.

## GET /health

Response:

```json
{
  "status": "ok",
  "version": "0.2.0",
  "model_provider_configured": true
}
```

`model_provider_configured` is a boolean only — whether a server-side model API
key is present. The key itself never leaves the server, and the frontend never
holds one.
