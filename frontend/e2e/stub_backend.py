"""A controlled backend for the Phase 14 browser tests.

Run it on the port the Vite dev server proxies to:

    backend/.venv/Scripts/python.exe frontend/e2e/stub_backend.py

Why a stub and not the real backend: the flows these tests exist to check are
*safety states* - a withheld finding, an incomplete document, a provider
failure, an unsupported answer - and reaching each of them through the real
system means a real model call that may or may not produce that state today.
The stub fixes the state and leaves the browser to show it, which is the part
under test. The backend's own behaviour is covered by 1300+ deterministic
tests that do use the real code.

The payloads below mirror `backend/app/schemas/` exactly. If the schemas
change, these fixtures are wrong and the browser tests fail - which is the
intended signal, not an inconvenience.

Scenario selection is by uploaded filename, so a test chooses its state by
choosing which file to upload:

    verified.pdf          one finding, verified, with evidence
    withheld.pdf          nothing shown; two findings withheld
    incomplete.pdf        extraction leaves a page unread; analysis blocked
    provider-failure.pdf  the analysis fails with a provider error
    qa-failure.pdf        the analysis succeeds; only Q&A fails
    qa-recovers.pdf       the analysis succeeds; Q&A fails once, then answers
    notfound.pdf          Q&A returns the not-found fallback
    interpretation.pdf    one verified claim with an unverified explanation
    novalues.pdf          fully processed, but no values detected
    notext.pdf            fully processed, but no text could be read
    recovers.pdf          the analysis fails once, then succeeds on retry
    reasoning.pdf         two findings, provenance, one reasoning note (one withheld)
    reasoning-failed.pdf  two findings; the reasoning stage failed
    tamil.pdf             Tamil translations beside checked English text
    gemini-missing.pdf    the analysis fails: the analysis provider has no key
    notes.txt             rejected at upload

Nothing here is imported by the application. It is a test double.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="Phase 14 browser-test stub")

#: document_id -> scenario name, remembered from the upload.
SCENARIOS: dict[str, str] = {}

#: Which documents have had `extract` called on them.
EXTRACTED: set[str] = set()

#: document_id -> how many analyses have been started for it.
#:
#: Only `recovers.pdf` reads this. It is what lets one document return a
#: provider failure on the first attempt and a completed analysis on the
#: second, which is the only way to exercise the manual-retry path in the
#: browser: the real backend starts a genuinely new analysis after a failure,
#: and a stub that always answers the same thing cannot show that.
ATTEMPTS: dict[str, int] = {}

#: document_id -> how many questions have been asked about it.
#:
#: Only `qa-recovers.pdf` reads this, and for the same reason `ATTEMPTS` exists
#: for the analysis: showing that a second question clears the first one's
#: error needs a document that fails once and then answers.
ASKS: dict[str, int] = {}

DISCLAIMER = (
    "This is legal information drawn from your uploaded document, not legal advice. "
    "Check anything that matters against the document itself and with a qualified lawyer."
)

NOT_FOUND_ANSWER = (
    "I couldn't find this information in the uploaded document. "
    "That does not mean the document is silent on it - only that nothing could be "
    "confirmed, so nothing is shown."
)


def error(code: str, message: str, status: int, **details: Any) -> JSONResponse:
    """The project's standard error envelope (docs/07_API_SPEC.md)."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def scenario_for(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename or "", flags=re.IGNORECASE)
    return stem.lower() or "verified"


@app.post("/api/v1/documents/upload")
async def upload(file: UploadFile):
    name = file.filename or ""
    if not name.lower().endswith(".pdf"):
        return error(
            "invalid_file_type",
            "That file is not a PDF. Upload a PDF document of up to 25 MB.",
            415,
            filename=name,
        )

    scenario = scenario_for(name)
    document_id = f"doc_{scenario}"
    SCENARIOS[document_id] = scenario
    # A fresh upload is a fresh document, even when a previous test uploaded the
    # same fixture. Without this the second test to use a file inherits the
    # first one's extraction state and never sees the "read the document" step.
    EXTRACTED.discard(document_id)
    ASKS.pop(document_id, None)
    pages = 3
    return {
        "document_id": document_id,
        "filename": name,
        "page_count": pages,
        "size_bytes": 24_576,
        "content_type": "application/pdf",
        "status": "validated",
        "source_repaired": False,
    }


def _status_body(document_id: str, extracted: bool) -> dict[str, Any]:
    scenario = SCENARIOS.get(document_id, "verified")
    incomplete = scenario == "incomplete"

    if not extracted:
        return {
            "document_id": document_id,
            "status": "validated",
            "expected_pages": 3,
            "processed_pages": 0,
            "failed_pages": [],
            "unreadable_pages": [],
            "coverage_status": "pending",
            "coverage_explanation": "This document has not been read yet.",
            "analysis_eligible": False,
            "source_repaired": False,
        }

    if incomplete:
        return {
            "document_id": document_id,
            "status": "incomplete_document",
            "expected_pages": 3,
            "processed_pages": 2,
            "failed_pages": [],
            "unreadable_pages": [3],
            "coverage_status": "incomplete",
            "coverage_explanation": (
                "Page 3 of this document could not be read, so the analysis would be "
                "based on an incomplete document. Nothing is shown until every page "
                "has been read."
            ),
            "analysis_eligible": False,
            "source_repaired": False,
        }

    return {
        "document_id": document_id,
        "status": "ingested",
        "expected_pages": 3,
        "processed_pages": 3,
        "failed_pages": [],
        "unreadable_pages": [],
        "coverage_status": "complete",
        "coverage_explanation": "Every page of this document was read.",
        "analysis_eligible": True,
        "source_repaired": False,
    }


@app.get("/api/v1/documents/{document_id}/status")
async def status(document_id: str):
    return _status_body(document_id, document_id in EXTRACTED)


@app.post("/api/v1/documents/{document_id}/extract")
async def extract(document_id: str):
    EXTRACTED.add(document_id)
    scenario = SCENARIOS.get(document_id, "verified")
    incomplete = scenario == "incomplete"
    pages = [
        {
            "page_number": number,
            "status": "unreadable" if (incomplete and number == 3) else "processed",
            "text_length": 0 if (incomplete and number == 3) else 1200,
            "image_count": 1 if (incomplete and number == 3) else 0,
            "failure_reason": "no text layer" if (incomplete and number == 3) else None,
        }
        for number in (1, 2, 3)
    ]
    return {
        "document_id": document_id,
        "status": "incomplete_document" if incomplete else "ingested",
        "manifest": {
            "document_id": document_id,
            "total_pages": 3,
            "is_repaired": False,
            "extraction_method": "pymupdf",
            "pages": pages,
        },
        "coverage": {
            "status": "incomplete" if incomplete else "complete",
            "expected_pages": 3,
            "processed_pages": 2 if incomplete else 3,
            "failed_pages": [],
            "unreadable_pages": [3] if incomplete else [],
            "blocking_reasons": (
                ["Page 3 could not be read."] if incomplete else []
            ),
        },
    }


@app.get("/api/v1/documents/{document_id}/values")
async def values(document_id: str):
    """The Phase 17 deterministic value index.

    Mirrors `ValuesResponse`. Needs no model, so the stub serves it for every
    scenario including `provider-failure` - which is the point of the feature:
    the values are there whether or not the model ever ran.

    `novalues.pdf` exercises the empty state; an unextracted document is
    refused with the same 409 the real backend uses.

    `extraction` mirrors the Phase 18 field. The two empty scenarios differ
    only in it, which is what the panel now has to read to choose its wording:

        novalues.pdf  text was read, it simply states no amounts
        notext.pdf    nothing was read at all - possibly a scanned PDF
    """
    scenario = SCENARIOS.get(document_id, "verified")
    if document_id not in EXTRACTED or scenario == "incomplete":
        return error(
            "coverage_incomplete",
            "Values cannot be indexed because document processing is incomplete.",
            409,
            coverage_status="incomplete" if scenario == "incomplete" else "pending",
        )

    body = {
        "document_id": document_id,
        "coverage_status": "complete",
        "extraction": {"characters": 2400, "pages_with_text": 3, "pages_total": 3},
        "values": [],
    }
    if scenario == "novalues":
        return body

    if scenario == "notext":
        # Complete coverage and nothing read: a PDF whose pages carry neither
        # text nor images is covered, because there was nothing there to miss.
        body["extraction"] = {"characters": 0, "pages_with_text": 0, "pages_total": 3}
        return body

    if scenario == "provider-failure":
        # Values survive a provider failure - that is the point of the feature.
        # Deliberately excludes "30 days": flow 6 asserts that no model-derived
        # notice period appears once the model has failed, and this panel must
        # not be the thing that puts one on the screen.
        body["values"] = [
            {"kind": "currency", "value": "Rs 50,000", "page": 2, "ambiguous": False},
            {"kind": "date", "value": "1 April 2026", "page": 1, "ambiguous": False},
        ]
        return body

    body["values"] = [
        {"kind": "currency", "value": "Rs 50,000", "page": 2, "ambiguous": False},
        {"kind": "percentage", "value": "1.5%", "page": 2, "ambiguous": False},
        {"kind": "duration", "value": "30 days", "page": 2, "ambiguous": False},
        {"kind": "date", "value": "1 April 2026", "page": 1, "ambiguous": False},
        {"kind": "date", "value": "04/05/2026", "page": 1, "ambiguous": True},
    ]
    return body


@app.post("/api/v1/documents/{document_id}/analyze")
async def analyze(document_id: str):
    scenario = SCENARIOS.get(document_id, "verified")
    if scenario == "incomplete":
        return error(
            "incomplete_document",
            "This document could not be fully read, so it cannot be analysed. "
            "Page 3 has no readable text.",
            409,
            unreadable_pages=[3],
        )
    analysis_id = f"an_{scenario}"
    if scenario == "recovers":
        # A new id per attempt, exactly as the real runner issues after a
        # failure - so the frontend cannot appear to work by reusing the old one.
        ATTEMPTS[document_id] = ATTEMPTS.get(document_id, 0) + 1
        analysis_id = f"an_recovers-{ATTEMPTS[document_id]}"

    return {
        "analysis_id": analysis_id,
        "document_id": document_id,
        "status": "queued",
        "stage": "queued",
        "created_at": "2026-09-20T12:00:00Z",
        "reused": False,
    }


COVERAGE_SUMMARY = {
    "status": "complete",
    "expected_pages": 3,
    "processed_pages": 3,
    "failed_pages": [],
    "unreadable_pages": [],
    "source_repaired": False,
}


@app.get("/api/v1/analysis/{analysis_id}/status")
async def analysis_status(analysis_id: str):
    scenario = analysis_id.removeprefix("an_")
    if scenario == "recovers-1":
        scenario = "provider-failure"
    elif scenario.startswith("recovers-"):
        scenario = "recovers"

    if scenario == "gemini-missing":
        return {
            "analysis_id": analysis_id,
            "document_id": f"doc_{scenario}",
            "status": "failed",
            "stage": "analyzing",
            "created_at": "2026-09-20T12:00:00Z",
            "started_at": "2026-09-20T12:00:01Z",
            "completed_at": "2026-09-20T12:00:02Z",
            "duration_ms": 900,
            "coverage": COVERAGE_SUMMARY,
            "proposed_count": None,
            "verified_count": None,
            "withheld_count": None,
            "error_category": "provider_not_configured",
            # SAFE_MESSAGES[ModelNotConfiguredError] in backend/app/models/errors.py
            "error_message": "Document analysis is not available: the service is not configured.",
        }

    if scenario == "provider-failure":
        return {
            "analysis_id": analysis_id,
            "document_id": f"doc_{scenario}",
            "status": "failed",
            "stage": "analyzing",
            "created_at": "2026-09-20T12:00:00Z",
            "started_at": "2026-09-20T12:00:01Z",
            "completed_at": "2026-09-20T12:00:09Z",
            "duration_ms": 8000,
            "coverage": COVERAGE_SUMMARY,
            "proposed_count": None,
            "verified_count": None,
            "withheld_count": None,
            "error_category": "provider_unavailable",
            "error_message": "The analysis service is temporarily unavailable. Please try again.",
        }

    withheld = 2 if scenario == "withheld" else 0
    verified = 0 if scenario == "withheld" else 1
    return {
        "analysis_id": analysis_id,
        "document_id": f"doc_{scenario}",
        "status": "completed",
        "stage": "done",
        "created_at": "2026-09-20T12:00:00Z",
        "started_at": "2026-09-20T12:00:01Z",
        "completed_at": "2026-09-20T12:00:12Z",
        "duration_ms": 11000,
        "coverage": COVERAGE_SUMMARY,
        "proposed_count": verified + withheld,
        "verified_count": verified,
        "withheld_count": withheld,
        "error_category": None,
        "error_message": None,
    }


VERIFIED_FINDING = {
    "id": "f_001",
    "type": "termination",
    "claim": "Either party may terminate this agreement by giving 30 days' written notice.",
    "evidence": {
        "page": 2,
        "quote": "Either party may terminate this agreement by providing 30 days' written notice.",
        "section": "7. Termination",
    },
    "explanation": (
        "Either side can end the agreement early, as long as they tell the other side "
        "30 days beforehand and do it in writing."
    ),
    # Derived by the backend from the quoted text, never sent by the model.
    "attention": "review",
    # This explanation restates the clause, so the backend could establish it.
    "explanation_verified": True,
    "verification_status": "verified",
}

#: The same finding with an explanation the evidence does not establish - the
#: ordinary case, since an explanation is interpretation. The UI must label it.
INTERPRETED_FINDING = {
    **VERIFIED_FINDING,
    "explanation": (
        "In practice you can walk away from this deal as long as you give the other "
        "side a month's warning in writing."
    ),
    "explanation_verified": False,
}


#: The overview's closed topic list, mirroring
#: `CATEGORY_ORDER` / `CATEGORY_LABELS` / `ALWAYS_SHOWN` in
#: `backend/app/documents/overview.py`. `other` is published only when it has
#: items, exactly as the real projection does.
OVERVIEW_TOPICS: list[tuple[str, str]] = [
    ("parties_roles", "Parties and roles"),
    ("term_renewal", "Term and renewal"),
    ("fees_payments", "Fees and payments"),
    ("termination", "Termination"),
    ("confidentiality", "Confidentiality"),
    ("liability", "Liability"),
    ("notices", "Notices"),
    ("governing_law", "Governing law"),
]

#: Enough of `_KEYWORDS` to cover the types these fixtures use. The stub is a
#: test double, not a second implementation: if a fixture grows a type that is
#: not here it lands in `other`, which is what the real mapping would do too.
OVERVIEW_KEYWORDS = {
    "termination": "termination",
    "payment": "fees_payments",
    "confidentiality": "confidentiality",
}

#: Mirrors `EMPTY_MESSAGE`. The browser tests assert this sentence, because
#: the wording is the safety property: it reports what the application
#: released and never what the document contains.
OVERVIEW_EMPTY_MESSAGE = "No verified finding was released for this category."


def _overview(result: dict[str, Any]) -> dict[str, Any]:
    """Group a gated result exactly as `build_overview` does.

    Derived from `result["findings"]` rather than hand-written per scenario,
    so a stub fixture cannot put something in the overview that is not in the
    findings beside it - which is the invariant the browser flows check.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in result["findings"]:
        key = OVERVIEW_KEYWORDS.get(item["type"], "other")
        grouped.setdefault(key, []).append(
            {
                "finding_id": item["id"],
                "claim": item["claim"],
                "quote": item["evidence"]["quote"],
                "page": item["evidence"]["page"],
                "section": item["evidence"]["section"],
                "label": item["type"],
            }
        )

    categories = []
    for key, label in OVERVIEW_TOPICS:
        items = grouped.get(key, [])
        categories.append(
            {
                "key": key,
                "label": label,
                "items": items,
                "empty_message": None if items else OVERVIEW_EMPTY_MESSAGE,
            }
        )
    if grouped.get("other"):
        categories.append(
            {
                "key": "other",
                "label": "Other clauses",
                "items": grouped["other"],
                "empty_message": None,
            }
        )

    return {
        "categories": categories,
        "released_count": len(result["findings"]),
        "proposed_count": result["proposed_count"],
        "withheld_count": result["withheld"]["total"],
    }


# --- Phase 23 fixtures ---------------------------------------------------------

POLICY_VERSION = "2026-09-23.phase23"
#: Mirrors `REASONING_NOTE_LABEL` in backend/app/schemas/analysis.py.
REASONING_NOTE_LABEL = "Reasoning note \u2014 not independently verified"
TAMIL_EXPLANATION = "இரு தரப்பினரும் 30 நாட்கள் எழுத்துமூல அறிவிப்புடன் ஒப்பந்தத்தை முடிக்கலாம்."
TAMIL_ANSWER = "இரு தரப்பினரும் 30 நாட்கள் எழுத்துமூல அறிவிப்புடன் முடிக்கலாம்."

FEES_FINDING = {
    "id": "f_002",
    "type": "payment",
    "claim": "The Client shall pay GBP 5,000 per month.",
    "evidence": {"page": 3, "quote": "The Client shall pay GBP 5,000 per month.", "section": None},
    "explanation": "",
    "attention": "review",
    "explanation_verified": False,
    "verification_status": "verified",
}


def _provenance(reasoning_provider):
    return {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "reasoning_provider": reasoning_provider,
        "reasoning_model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning" if reasoning_provider else None,
        "verification_policy_version": POLICY_VERSION,
        "status": "completed",
    }


def _two_findings(reasoning):
    return {
        "findings": [VERIFIED_FINDING, FEES_FINDING],
        "withheld": {"total": 0, "rejected": 0, "unverified": 0, "partially_verified": 0},
        "proposed_count": 2,
        "insufficient_evidence": False,
        "coverage": COVERAGE_SUMMARY,
        "language": "en",
        "provenance": _provenance("nemotron"),
        "reasoning": reasoning,
    }


PHASE23_RESULTS = {
    "reasoning": lambda: _two_findings({
        "status": "completed",
        "failure_kind": None,
        "provider": "nemotron",
        "notes": [{
            "id": "n_001",
            "category": "dependency",
            "text": "The 30 days' notice period and the monthly fee should be read together: "
                    "fees may continue to fall due during the notice period.",
            "finding_ids": ["f_001", "f_002"],
            "quotes": ["Either party may terminate this agreement by providing 30 days' written notice."],
            "evidence_checked": True,
            "label": REASONING_NOTE_LABEL,
        }],
        "withheld_count": 1,
    }),
    "reasoning-failed": lambda: _two_findings({
        "status": "failed",
        "failure_kind": "capacity",
        "provider": "nemotron",
        "notes": [],
        "withheld_count": 0,
    }),
    "tamil": lambda: {
        "findings": [{
            **VERIFIED_FINDING,
            "explanation_translation": TAMIL_EXPLANATION,
            "explanation_translation_language": "ta",
        }],
        "withheld": {"total": 0, "rejected": 0, "unverified": 0, "partially_verified": 0},
        "proposed_count": 1,
        "insufficient_evidence": False,
        "coverage": COVERAGE_SUMMARY,
        "language": "ta",
        "provenance": _provenance(None),
        "reasoning": {"status": "disabled", "failure_kind": None, "provider": None,
                      "notes": [], "withheld_count": 0},
    },
}

@app.get("/api/v1/documents/{document_id}/findings")
async def findings(document_id: str):
    scenario = SCENARIOS.get(document_id, "verified")
    if scenario in PHASE23_RESULTS:
        result = PHASE23_RESULTS[scenario]()
    elif scenario == "interpretation":
        result = {
            "findings": [INTERPRETED_FINDING],
            "withheld": {"total": 0, "rejected": 0, "unverified": 0, "partially_verified": 0},
            "proposed_count": 1,
            "insufficient_evidence": False,
            "coverage": COVERAGE_SUMMARY,
        }
    elif scenario == "withheld":
        result = {
            "findings": [],
            "withheld": {
                "total": 2,
                "rejected": 1,
                "unverified": 1,
                "partially_verified": 0,
            },
            "proposed_count": 2,
            "insufficient_evidence": True,
            "coverage": COVERAGE_SUMMARY,
        }
    else:
        result = {
            "findings": [VERIFIED_FINDING],
            "withheld": {
                "total": 1,
                "rejected": 1,
                "unverified": 0,
                "partially_verified": 0,
            },
            "proposed_count": 2,
            "insufficient_evidence": False,
            "coverage": COVERAGE_SUMMARY,
        }
    return {
        "document_id": document_id,
        "analysis_id": f"an_{scenario}",
        "status": "completed",
        "result": result,
        "overview": _overview(result),
    }


#: What `/ask` returns when the provider is down, mirroring
#: `QUESTION_SAFE_MESSAGES[ModelUnavailableError]` and the `model_unavailable`
#: code in `backend/app/models/errors.py`.
#:
#: The wording is the point of these fixtures. A question that fails says so
#: about the question; it must not say the analysis service failed, because a
#: user looking at completed results would read that as their results being
#: withdrawn.
QA_UNAVAILABLE = (
    "The question service is temporarily unavailable. No answer was "
    "generated or shown. You can ask again later."
)


@app.post("/api/v1/documents/{document_id}/ask")
async def ask(document_id: str, request: Request):
    body = await request.json()
    question = body.get("question", "")
    scenario = SCENARIOS.get(document_id, "verified")

    ASKS[document_id] = ASKS.get(document_id, 0) + 1

    # `provider-failure` fails everything; `qa-failure` fails only this, with a
    # completed analysis still on screen; `qa-recovers` fails only the first.
    down = scenario in {"provider-failure", "qa-failure"} or (
        scenario == "qa-recovers" and ASKS[document_id] == 1
    )
    if down:
        return error("model_unavailable", QA_UNAVAILABLE, 503, reason="provider_capacity")

    language = body.get("language", "en")

    if scenario == "notfound" or "governing law" in question.lower():
        return {
            "document_id": document_id,
            "question": question,
            "answer": NOT_FOUND_ANSWER,
            "status": "not_found",
            "evidence": [],
            "withheld_evidence": 1,
            "claims_checked": 0,
            "claims_withheld": 0,
            "disclaimer": DISCLAIMER,
        }

    return {
        "document_id": document_id,
        "question": question,
        "answer": "Either party may terminate this agreement by providing 30 days' written notice.",
        "status": "supported",
        "evidence": [
            {
                "quote": "Either party may terminate this agreement by providing 30 days' written notice.",
                "page": 2,
                "section": "7. Termination",
                "verification_status": "verified",
                "note": "",
            }
        ],
        "withheld_evidence": 0,
        "claims_checked": 1,
        "claims_withheld": 0,
        # Mirrors `gate_answer`: a translation only for a non-English reader,
        # only beside a fully supported answer.
        "answer_translation": TAMIL_ANSWER if language == "ta" else None,
        "answer_translation_language": "ta" if language == "ta" else None,
        "provenance": {
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "reasoning_provider": None,
            "reasoning_model": None,
            "verification_policy_version": POLICY_VERSION,
            "status": "supported",
        },
        "disclaimer": DISCLAIMER,
    }


@app.delete("/api/v1/documents/{document_id}")
async def discard(document_id: str):
    SCENARIOS.pop(document_id, None)
    EXTRACTED.discard(document_id)
    ASKS.pop(document_id, None)
    # Mirrors routes_documents.delete_document: a 204 carries no body. A JSON
    # `null` here made uvicorn abort the response mid-send.
    return Response(status_code=204)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "stub": True}


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
