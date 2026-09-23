"""The model-provider abstraction.

Business logic depends on this interface, never on a vendor SDK
(docs/02_ARCHITECTURE.md sec. 7). Swapping Nemotron for another model means
adding one subclass; the coverage gate, the verifier and the output gate do not
change, because none of them import a provider.

What a provider returns is a PROPOSAL. It is the input to
`app.verification.grounding.verify_finding`, never a result in its own right.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, ValidationError

from app.models.errors import ModelResponseError, make_error
from app.models.payload import DocumentPayload
from app.schemas.findings import ModelAnalysis, ModelAnswer


class AnalysisRequest(BaseModel):
    """Ask a model to identify clauses in a document."""

    payload: DocumentPayload


class QuestionRequest(BaseModel):
    """Ask a model a question answerable only from the document."""

    payload: DocumentPayload
    question: str = Field(min_length=1, max_length=2000)


class ModelProvider(ABC):
    """What the application needs from any model."""

    name: str = "abstract"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has what it needs to make a request.

        A boolean only - never the credential itself.
        """

    @abstractmethod
    async def analyze_document(self, request: AnalysisRequest) -> ModelAnalysis:
        """Propose findings for a document. Raises `ModelError` on failure."""

    @abstractmethod
    async def answer_question(self, request: QuestionRequest) -> ModelAnswer:
        """Answer a question from the document. Raises `ModelError` on failure."""


# --- Response parsing -------------------------------------------------------
#
# Shared by every provider: reasoning models wrap their answer in prose or
# thinking traces regardless of vendor, so the extraction is the same problem
# each time.

#: Reasoning traces emitted by models that think before answering.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)

#: ```json ... ``` fences.
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_object(raw: str) -> dict:
    """Pull a single JSON object out of a model's reply.

    Tolerant of the packaging models add - thinking traces, code fences, a
    sentence of preamble - and intolerant of anything else. If no valid object
    can be found this raises rather than returning a partial structure.
    """
    if not raw or not raw.strip():
        raise make_error(ModelResponseError, detail="empty_response")

    text = _THINK_BLOCK.sub("", raw)
    text = _UNCLOSED_THINK.sub("", text).strip()

    fenced = _CODE_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    # Try the whole thing, then the outermost braced span.
    for candidate in (text, _outermost_object(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed

    raise make_error(ModelResponseError, detail="no_json_object")


def _outermost_object(text: str) -> str | None:
    """The span from the first '{' to its matching '}', respecting strings."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def parse_analysis(raw: str) -> ModelAnalysis:
    """Validate a reply against the analysis schema."""
    return _validate(ModelAnalysis, extract_json_object(raw))


def parse_answer(raw: str) -> ModelAnswer:
    """Validate a reply against the answer schema."""
    return _validate(ModelAnswer, extract_json_object(raw))


def _validate(schema: type[BaseModel], data: dict):
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        # Field names only. Error details can quote the offending value, which
        # for these schemas is document text.
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise make_error(
            ModelResponseError, detail=f"schema_invalid:{','.join(fields)[:120]}"
        ) from exc
