"""Shared test fixtures.

Every test here is deterministic and offline: no NVIDIA API calls are made
(docs/06_EVALUATION_PLAN.md, "API Usage Strategy").
"""

from __future__ import annotations

import os

# --- Test environment, fixed before the app is imported ----------------------
# Set in the process environment, which outranks any developer .env file, so a
# local key or role choice can never change what the suite exercises.
#
# The pre-Phase-23 suite was written against Nemotron in both roles, with no
# reasoning stage and no persistence; that is pinned here so those tests run
# exactly as written. Phase 23 tests select Gemini, reasoning and persistence
# explicitly, per test. Keys are blank: no default test reaches a real provider.
os.environ["ANALYSIS_PROVIDER"] = "nemotron"
os.environ["QA_PROVIDER"] = "nemotron"
os.environ["REASONING_PROVIDER"] = "nemotron"
os.environ["REASONING_ENABLED"] = "false"
os.environ["GEMINI_MODEL"] = "gemini-test-model"
os.environ["GEMINI_API_KEY"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.documents.storage import document_store
from app.main import create_app


def make_pdf(pages: int = 3, text: str = "Sample agreement text.") -> bytes:
    """Build a small in-memory PDF with one line of text per page."""
    document = fitz.open()
    try:
        for index in range(pages):
            page = document.new_page()
            page.insert_text((72, 72), f"Page {index + 1}. {text}")
        return document.tobytes()
    finally:
        document.close()


def make_pdf_with_blank_pages(total: int, blank: set[int]) -> bytes:
    """PDF where pages in `blank` carry no text and no images."""
    document = fitz.open()
    try:
        for index in range(total):
            page = document.new_page()
            if (index + 1) not in blank:
                page.insert_text((72, 72), f"Page {index + 1} has real contract text.")
        return document.tobytes()
    finally:
        document.close()


def _tiny_png() -> bytes:
    """A valid 2x2 greyscale PNG, built rather than hard-coded so its CRCs are right."""
    import struct
    import zlib

    width = height = 2
    # Each row is one filter byte (0 = none) followed by one white pixel per column.
    raw = (bytes([0]) + bytes([255]) * width) * height

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    return (
        bytes([137, 80, 78, 71, 13, 10, 26, 10])
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def make_pdf_with_image_only_page(total: int, image_page: int) -> bytes:
    """PDF where `image_page` carries an image but no text layer.

    This is what a scanned page looks like to a text extractor.
    """
    document = fitz.open()
    try:
        for index in range(total):
            page = document.new_page()
            if (index + 1) == image_page:
                page.insert_image(fitz.Rect(72, 72, 172, 172), stream=_tiny_png())
            else:
                page.insert_text((72, 72), f"Page {index + 1} has real contract text.")
        return document.tobytes()
    finally:
        document.close()


@pytest.fixture(autouse=True)
def no_live_provider(request, monkeypatch):
    """No default test may reach a real model provider.

    Individual tests inject a fake provider, but that is a discipline rather
    than a guarantee: a route that resolves the configured provider itself
    will happily build a real one if a key is present, and a developer's `.env`
    supplies one. That is exactly how a synchronous `/ask` endpoint turned a
    unit test into a metered NVIDIA call during Phase 9.

    Blanking the key closes the hole structurally. An unfaked provider now
    raises `ModelNotConfiguredError` - a loud, offline failure - instead of
    quietly spending money and sending document text to a third party.

    The one live test is marked `live` and keeps the real environment.
    """
    if "live" in request.keywords:
        yield
        return
    # An empty value beats the .env file: environment wins in pydantic-settings.
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Point the ephemeral workspace at a per-test temp directory."""
    get_settings.cache_clear()
    monkeypatch.setenv("TEMP_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024))
    monkeypatch.setenv("MAX_PAGES", "50")
    get_settings.cache_clear()
    yield
    document_store.clear()
    get_settings.cache_clear()


@pytest.fixture
def client(isolated_workspace):
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf()


def upload(client: TestClient, content: bytes, filename: str = "contract.pdf",
           content_type: str = "application/pdf"):
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, content_type)},
    )
