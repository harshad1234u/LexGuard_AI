"""Phase 23: optional metadata persistence.

No test here reaches Supabase. The repository is exercised through
`httpx.MockTransport`, and the migration is checked statically; a live RLS
check needs an approved database and is not part of the default suite.
"""

from __future__ import annotations

import json
import pathlib
import re

import httpx
import pytest

from app.agents.runner import analysis_runner
from app.core.config import Settings, get_settings
from app.persistence import NullRepository, get_repository, set_repository
from app.persistence.supabase import SCHEMA_VERSION, SupabaseRepository, filename_digest
from tests.conftest import upload
from tests.test_api_analysis import wait_for_terminal
from tests.test_workflow import FakeProvider, single_page_pdf

MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0001_lexguard_metadata.sql"
SERVICE_KEY = "sb-service-role-canary-phase23"
FILENAME = "Confidential Settlement - Jane Doe.pdf"

PAGE = (
    "SERVICES AGREEMENT\n"
    "2. Termination. Either party may terminate this agreement by providing "
    "30 days' written notice.\n"
)
GOOD = {
    "id": "f_ok",
    "type": "termination",
    "claim": "Either party may terminate with 30 days' written notice.",
    "evidence": {"page": 1, "section": None, "quote": "30 days' written notice"},
    "explanation": "",
}
WITHHELD = {
    "id": "f_bad",
    "type": "liability",
    "claim": "The Supplier's liability is unlimited.",
    "evidence": {"page": 1, "section": None, "quote": "liability is unlimited"},
    "explanation": "",
}


class SpyRepository(NullRepository):
    """Records every call the application makes, and everything passed."""

    enabled = True

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def record_document(self, **kwargs):
        self.calls.append(("record_document", kwargs))

    def record_analysis(self, **kwargs):
        self.calls.append(("record_analysis", kwargs))

    def record_answer(self, document_id, response, **kwargs):
        self.calls.append(("record_answer", {"document_id": document_id, "response": response, **kwargs}))

    def delete_document(self, document_id):
        self.calls.append(("delete_document", {"document_id": document_id}))

    def dump(self) -> str:
        def render(value):
            if hasattr(value, "model_dump_json"):
                return value.model_dump_json()
            return str(value)

        return "\n".join(f"{name} " + " ".join(render(v) for v in args.values())
                         for name, args in self.calls)


@pytest.fixture
def spy():
    repository = SpyRepository()
    set_repository(repository)
    analysis_runner.clear()
    yield repository
    set_repository(None)
    analysis_runner.clear()


class TestDefault:
    def test_the_default_repository_stores_nothing(self):
        set_repository(None)
        assert isinstance(get_repository(), NullRepository)
        assert get_repository().enabled is False


class TestPrivacyAtTheBoundary:
    def test_only_released_content_reaches_the_repository(self, client, monkeypatch, spy):
        provider = FakeProvider(findings=[GOOD, WITHHELD])
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: provider)
        response = upload(client, single_page_pdf(PAGE), filename=FILENAME)
        document_id = response.json()["document_id"]
        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        assert wait_for_terminal(client, analysis_id)["status"] == "completed"

        [analysis] = [kw for name, kw in spy.calls if name == "record_analysis"]
        assert [f.id for f in analysis["result"].findings] == ["f_ok"]
        dumped = spy.dump()
        assert "unlimited" not in dumped, "withheld text reached persistence"
        assert "SERVICES AGREEMENT" not in dumped, "page text reached persistence"

    def test_a_failed_analysis_passes_no_result(self, client, monkeypatch, spy):
        from app.models.errors import ModelUnavailableError, make_error

        provider = FakeProvider(raises=make_error(ModelUnavailableError, detail="provider_capacity"))
        monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: provider)
        document_id = upload(client, single_page_pdf(PAGE)).json()["document_id"]
        analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
        assert wait_for_terminal(client, analysis_id)["status"] == "failed"
        [analysis] = [kw for name, kw in spy.calls if name == "record_analysis"]
        assert analysis["result"] is None
        assert analysis["failure_kind"] == "capacity"

    def test_answer_metadata_carries_no_question_or_answer_text(self, client, monkeypatch, spy):
        from tests.test_api_qa import FakeProvider as QaProvider
        from tests.test_api_qa import contract_pdf

        provider = QaProvider()
        monkeypatch.setattr("app.api.v1.routes_qa._provider_factory", lambda: provider)
        document_id = upload(client, contract_pdf()).json()["document_id"]
        client.post(f"/api/v1/documents/{document_id}/extract")
        client.post(f"/api/v1/documents/{document_id}/ask",
                    json={"question": "What is the secret notice period?"})

        [call] = [kw for name, kw in spy.calls if name == "record_answer"]
        row = SupabaseRepository.answer_row(
            call["document_id"], call["response"], question_language=call["question_language"]
        )
        text = json.dumps(row)
        assert "secret notice" not in text
        assert "terminate" not in text
        assert row["answer_status"] == "supported"

    def test_discarding_a_document_deletes_its_metadata(self, client, spy):
        document_id = upload(client, single_page_pdf(PAGE)).json()["document_id"]
        assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
        assert ("delete_document", {"document_id": document_id}) in spy.calls

    def test_ttl_expiry_deletes_metadata_too(self, client, monkeypatch, spy):
        from app.documents.storage import document_store

        document_id = upload(client, single_page_pdf(PAGE)).json()["document_id"]
        monkeypatch.setenv("DOCUMENT_TTL_SECONDS", "-1")
        get_settings.cache_clear()
        assert document_store.purge_expired() >= 1
        assert ("delete_document", {"document_id": document_id}) in spy.calls

    def test_a_repository_failure_never_affects_the_response(self, client, monkeypatch):
        class Broken(SpyRepository):
            def record_analysis(self, **kwargs):
                raise RuntimeError("database down")

            def record_document(self, **kwargs):
                raise RuntimeError("database down")

        set_repository(Broken())
        analysis_runner.clear()
        try:
            monkeypatch.setattr("app.agents.runner.get_model_provider", lambda: FakeProvider(findings=[GOOD]))
            document_id = upload(client, single_page_pdf(PAGE)).json()["document_id"]
            analysis_id = client.post(f"/api/v1/documents/{document_id}/analyze").json()["analysis_id"]
            body = wait_for_terminal(client, analysis_id)
            assert body["status"] == "completed"
            assert body["verified_count"] == 1
        finally:
            set_repository(None)
            analysis_runner.clear()


# --- The Supabase repository, over a mock transport ----------------------------

def supabase_settings(monkeypatch) -> Settings:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    monkeypatch.setenv("PERSISTENCE_HASH_SALT", "pepper")
    get_settings.cache_clear()
    return get_settings()


class Recorder:
    def __init__(self, schema=SCHEMA_VERSION, schema_status=200, write_status=201, explode=False):
        self.requests: list[httpx.Request] = []
        self.schema, self.schema_status = schema, schema_status
        self.write_status, self.explode = write_status, explode

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/rpc/lexguard_schema_version"):
            return httpx.Response(self.schema_status, json=self.schema)
        if self.explode:
            raise httpx.ConnectError("down")
        return httpx.Response(self.write_status)

    def bodies(self) -> str:
        return "\n".join(r.content.decode() for r in self.requests)


def repository(monkeypatch, recorder: Recorder) -> SupabaseRepository:
    return SupabaseRepository(supabase_settings(monkeypatch), transport=httpx.MockTransport(recorder))


class TestSupabaseRepository:
    def test_a_missing_schema_disables_every_write(self, monkeypatch):
        recorder = Recorder(schema_status=404, schema={"message": "function not found"})
        repo = repository(monkeypatch, recorder)
        assert repo.enabled is False
        repo.record_document(document_id="doc_1", filename=FILENAME, page_count=1, detected_language="en")
        repo.close()
        assert len(recorder.requests) == 1, "only the schema probe may be sent"

    def test_a_wrong_schema_version_disables_writes(self, monkeypatch):
        repo = repository(monkeypatch, Recorder(schema="0"))
        assert repo.enabled is False

    def test_the_service_key_is_sent_as_auth_and_nowhere_else(self, monkeypatch):
        recorder = Recorder()
        repo = repository(monkeypatch, recorder)
        repo.record_document(document_id="doc_1", filename=FILENAME, page_count=2, detected_language="en")
        repo.close()
        assert repo.enabled is True
        write = recorder.requests[-1]
        assert write.headers["Authorization"] == f"Bearer {SERVICE_KEY}"
        assert SERVICE_KEY not in recorder.bodies()
        assert str(write.url).startswith("https://project.supabase.co/rest/v1/documents")

    def test_the_raw_filename_is_never_sent(self, monkeypatch):
        recorder = Recorder()
        repo = repository(monkeypatch, recorder)
        repo.record_document(document_id="doc_1", filename=FILENAME, page_count=2, detected_language="en")
        repo.close()
        row = json.loads(recorder.requests[-1].content)
        assert "Jane Doe" not in recorder.bodies()
        assert row["filename_sha256"] == filename_digest(FILENAME, "pepper")
        assert row["file_extension"] == "pdf"
        assert set(row) == {"id", "filename_sha256", "file_extension", "page_count",
                            "detected_language", "expires_at"}

    def test_delete_targets_one_document_by_id(self, monkeypatch):
        recorder = Recorder()
        repo = repository(monkeypatch, recorder)
        repo.delete_document("doc_abc")
        repo.close()
        request = recorder.requests[-1]
        assert request.method == "DELETE"
        assert request.url.path == "/rest/v1/documents"
        assert dict(request.url.params) == {"id": "eq.doc_abc"}

    def test_purge_deletes_only_expired_documents(self, monkeypatch):
        recorder = Recorder()
        repo = repository(monkeypatch, recorder)
        repo.purge_expired()
        repo.close()
        request = recorder.requests[-1]
        assert request.method == "DELETE"
        assert request.url.path == "/rest/v1/documents"
        params = dict(request.url.params)
        assert list(params) == ["expires_at"]
        assert params["expires_at"].startswith("lt.")

    @pytest.mark.parametrize("recorder", [Recorder(write_status=500), Recorder(explode=True)])
    def test_write_failures_are_swallowed(self, monkeypatch, recorder):
        repo = repository(monkeypatch, recorder)
        repo.record_document(document_id="d", filename="a.pdf", page_count=1, detected_language="en")
        repo.delete_document("d")
        repo.close()  # waits for the pool; no exception escapes

    def test_analysis_rows_carry_released_findings_only(self):
        from app.schemas.analysis import AnalysisResult, VerifiedFindingOut, WithheldSummary
        from app.schemas.findings import Evidence
        from app.schemas.provenance import Provenance

        result = AnalysisResult(
            findings=[
                VerifiedFindingOut(
                    id="f_ok", type="termination", claim="c",
                    evidence=Evidence(page=1, quote="q"), verification_status="verified",
                )
            ],
            withheld=WithheldSummary(total=3, rejected=3),
            proposed_count=4,
            provenance=Provenance(provider="gemini", model="m", verification_policy_version="v",
                                  status="completed"),
        )
        job, findings = SupabaseRepository.analysis_rows(
            document_id="d", analysis_id="an", status="completed", duration_ms=5,
            failure_kind=None, result=result,
        )
        assert (job["released_count"], job["withheld_count"], job["proposed_count"]) == (1, 3, 4)
        assert job["provider"] == "gemini"
        assert [f["finding_id"] for f in findings] == ["f_ok"]
        assert all(f["verification_status"] == "verified" for f in findings)


class TestMigration:
    # Comments stripped: the header explains what is absent, and a check for
    # absence must look at statements, not at that explanation.
    SQL = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).lower()
    TABLES = ("documents", "analysis_jobs", "released_findings", "qa_events")

    def test_rls_is_enabled_on_every_table(self):
        for table in self.TABLES:
            assert f"alter table public.{table}" in self.SQL
            assert re.search(rf"alter table public\.{table}\s+enable row level security", self.SQL)

    def test_no_policy_grants_browser_roles_access(self):
        assert "create policy" not in self.SQL
        assert "revoke all on public.documents" in self.SQL
        assert "from anon, authenticated" in self.SQL
        assert not re.search(r"grant [^;]* to (anon|authenticated)", self.SQL)

    def test_there_is_no_column_for_private_content(self):
        for forbidden in ("page_text", "extracted_text", "question_text", "answer_text",
                          "original_filename", "prompt", "api_key", " filename "):
            assert forbidden not in self.SQL, forbidden

    def test_released_findings_can_only_hold_verified_rows(self):
        assert "check (verification_status = 'verified')" in self.SQL

    def test_everything_cascades_from_a_document(self):
        assert self.SQL.count("on delete cascade") == 3

    def test_the_schema_probe_matches_the_code(self):
        assert f"select '{SCHEMA_VERSION}'::text" in self.SQL
        assert "grant execute on function public.lexguard_schema_version() to service_role" in self.SQL
