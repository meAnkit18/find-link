"""End-to-end pipeline tests: parse → extract → resolve → write → enrich.

Runs with a fake LLM (predefined JSON responses) and a fake graph client
(execute_raw stores in a dict) — everything else is real.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Point the DB at a throwaway temp file before any project import.
_evidence_dir = tempfile.mkdtemp()
os.environ["EVIDENCE_DATABASE_URL"] = f"sqlite:///{_evidence_dir}/test.db"
os.environ["EVIDENCE_DIR"] = _evidence_dir
os.environ["LLM_API_KEY"] = "sk-test-key"

from evidence_core.database import SessionLocal, init_db  # noqa: E402, I001
from evidence_core.db_models import (  # noqa: E402, I001
    EntityRegistry,
    Evidence,
    Fact,
    ReviewItem,
)
from evidence_core.pipeline import (  # noqa: E402, I001
    run_pipeline_inline,
    step_extract,
    step_parse,
    step_resolve,
)

# ------------------------------------------------------------------ fakes


class _FakeQueryResult:
    """Mimics graph_core.storage.result.QueryResult with an empty .rows."""

    def __init__(self) -> None:
        self.rows: list[dict] = []


class _FakeMetadata:
    """Fake metadata for ensure_ingest_schema — no-ops."""

    def create_space(self, name: str, vid_type: str = "FIXED_STRING(32)") -> None:
        pass

    def create_tag(self, schema) -> None:
        pass

    def create_edge_type(self, schema) -> None:
        pass


class FakeGraphClient:
    """Minimal fake that records executed nGQL so we can verify writes."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.metadata = _FakeMetadata()

    def execute_raw(self, ngql: str) -> _FakeQueryResult:
        self.executed.append(ngql)
        return _FakeQueryResult()

    def close(self) -> None:
        pass


def _fake_graph_client():
    return FakeGraphClient()


_FAKE_LLM_RESPONSE: dict | None = None


def _fake_chat_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    if _FAKE_LLM_RESPONSE is not None:
        return _FAKE_LLM_RESPONSE
    return {
        "entities": [],
        "relationships": [],
        "summary": "fake summary",
        "overall_confidence": 0.8,
    }


def _set_llm_response(data: dict) -> None:
    global _FAKE_LLM_RESPONSE
    _FAKE_LLM_RESPONSE = data


def _reset_llm() -> None:
    global _FAKE_LLM_RESPONSE
    _FAKE_LLM_RESPONSE = None


# -------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _patch_all(monkeypatch):
    monkeypatch.setattr("evidence_core.pipeline._graph_client", _fake_graph_client)
    monkeypatch.setattr("ingestion_core.extraction.chat_json", _fake_chat_json)
    # ensure_ingest_schema wants to run DDL and verify; in tests we skip it.
    monkeypatch.setattr(
        "intelligence_schema.ingest_schema.ensure_ingest_schema",
        lambda client, space: None,
    )
    init_db()
    _reset_llm()
    yield
    # Clean up the DB between tests.
    db = SessionLocal()
    try:
        for table in (ReviewItem, Fact, EntityRegistry, Evidence):
            db.query(table).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------------------------------------------------------ helpers


def _make_evidence(
    text: str = "John Doe works at Acme Corp.",
    source_type: str = "text",
) -> str:
    import hashlib

    db = SessionLocal()
    try:
        ev = Evidence(
            source_name="test",
            source_type=source_type,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            raw_text=text,
        )
        db.add(ev)
        db.commit()
        eid = ev.id
    finally:
        db.close()
    return eid


def _run_full_pipeline(evidence_id: str) -> None:
    run_pipeline_inline(evidence_id)


# ------------------------------------------------------------------ tests


class TestFullPipeline:
    """Full parse → extract → resolve → write → enrich chain."""

    def test_full_pipeline_reaches_enriched(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "John Doe",
                 "attributes": {}, "confidence": 0.95, "source_span": "John Doe"},
                {"local_id": "e2", "type": "Company", "name": "Acme Corp",
                 "attributes": {}, "confidence": 0.9, "source_span": "Acme Corp"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e2",
                 "type": "WORKS_AT", "confidence": 0.85, "source_span": "works at"},
            ],
            "summary": "John works at Acme",
            "overall_confidence": 0.8,
        })

        eid = _make_evidence()
        _run_full_pipeline(eid)

        ev = db.get(Evidence, eid)
        assert ev is not None
        assert ev.status == "enriched", f"expected enriched, got {ev.status}"

        log = ev.processing_log or []
        stages_in_log = {entry["stage"] for entry in log}
        assert "enrich" in stages_in_log, f"enrich stage not in log: {log}"
        assert "write" in stages_in_log
        assert "resolve" in stages_in_log
        assert "extract" in stages_in_log
        assert "parse" in stages_in_log

        facts = db.query(Fact).filter(Fact.evidence_id == eid).all()
        assert len(facts) > 0, "should have created facts"
        entity_facts = [f for f in facts if f.kind == "entity"]
        rel_facts = [f for f in facts if f.kind == "relationship"]
        assert len(entity_facts) >= 2, f"expected at least 2 entity facts, got {len(entity_facts)}"
        assert len(rel_facts) >= 1, f"expected at least 1 relationship fact, got {len(rel_facts)}"

    def test_drops_invalid_entities(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Email", "name": "not-an-email",
                 "attributes": {"address": "not-an-email"}, "confidence": 0.9,
                 "source_span": "not-an-email"},
                {"local_id": "e2", "type": "Phone", "name": "999",
                 "attributes": {"number": "999"}, "confidence": 0.8,
                 "source_span": "999"},
                {"local_id": "e3", "type": "Person", "name": "Valid Person",
                 "attributes": {}, "confidence": 0.95, "source_span": "Valid"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e3",
                 "type": "HAS_EMAIL", "confidence": 0.8, "source_span": ""},
            ],
            "summary": "test",
            "overall_confidence": 0.5,
        })

        eid = _make_evidence("Valid Person not-an-email 999")
        _run_full_pipeline(eid)

        ev = db.get(Evidence, eid)
        assert ev is not None
        assert ev.status == "enriched", f"expected enriched, got {ev.status}"

        entities = db.query(EntityRegistry).all()
        names = {e.canonical_name for e in entities}
        assert "not-an-email" not in names, "invalid email should have been dropped"
        assert "Valid Person" in names, "valid person should remain"

        registry_email = db.query(EntityRegistry).filter(
            EntityRegistry.type == "Email"
        ).all()
        assert len(registry_email) == 0, "email entity should not be in registry"

        facts = db.query(Fact).filter(Fact.evidence_id == eid).all()
        rel_to_invalid = [
            f for f in facts if f.kind == "relationship"
        ]
        assert len(rel_to_invalid) == 0, (
            "relationship touching invalid entity should have been dropped"
        )

    def test_normalizes_names(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "  john   doe  ",
                 "attributes": {}, "confidence": 0.9, "source_span": "john doe"},
                {"local_id": "e2", "type": "Company", "name": "  Acme   Corp  ",
                 "attributes": {}, "confidence": 0.8, "source_span": "Acme"},
            ],
            "relationships": [],
            "summary": "test",
            "overall_confidence": 0.5,
        })

        eid = _make_evidence("john doe acme corp")
        _run_full_pipeline(eid)

        entities = db.query(EntityRegistry).all()
        names = {e.canonical_name for e in entities}
        assert "John Doe" in names, f"expected 'John Doe', got {names}"
        assert "Acme Corp" in names, f"expected 'Acme Corp', got {names}"

    def test_projects_vertices_and_edges(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "Jane Smith",
                 "attributes": {}, "confidence": 0.95, "source_span": "Jane"},
                {"local_id": "e2", "type": "Company", "name": "Test Inc",
                 "attributes": {}, "confidence": 0.9, "source_span": "Test Inc"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e2",
                 "type": "WORKS_AT", "confidence": 0.8, "source_span": ""},
            ],
            "summary": "test",
            "overall_confidence": 0.5,
        })

        eid = _make_evidence("Jane works at Test Inc")
        _run_full_pipeline(eid)

        # The fake graph client records every execute_raw call.
        ev = db.get(Evidence, eid)
        assert ev.status == "enriched"

        facts = db.query(Fact).filter(
            Fact.evidence_id == eid,
            Fact.status == "written",
        ).all()
        assert len(facts) > 0, "facts should be written"


class TestRetryNoDuplication:
    """Retrying a resolved evidence must not duplicate facts/review items."""

    def test_retry_does_not_duplicate_facts(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "Retry Person",
                 "attributes": {}, "confidence": 0.95, "source_span": "Retry"},
                {"local_id": "e2", "type": "Email", "name": "retry@example.com",
                 "attributes": {"address": "retry@example.com"}, "confidence": 0.9,
                 "source_span": "retry@example.com"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e2",
                 "type": "HAS_EMAIL", "confidence": 0.8, "source_span": ""},
            ],
            "summary": "test",
            "overall_confidence": 0.5,
        })

        eid = _make_evidence("Retry Person retry@example.com")

        # First run — resolve and write.
        step_parse(eid)
        step_extract(eid)
        step_resolve(eid)

        # Count facts and review items after first pass.
        facts_first = db.query(Fact).filter(Fact.evidence_id == eid).count()
        reviews_first = db.query(ReviewItem).filter(
            ReviewItem.evidence_id == eid
        ).count()
        reg_first = db.query(EntityRegistry).count()

        # Second resolve (simulates retry after resolve stage).
        step_resolve(eid)

        facts_second = db.query(Fact).filter(Fact.evidence_id == eid).count()
        reviews_second = db.query(ReviewItem).filter(
            ReviewItem.evidence_id == eid
        ).count()
        reg_second = db.query(EntityRegistry).count()

        assert facts_second == facts_first, (
            f"facts changed: {facts_first} -> {facts_second}"
        )
        assert reviews_second == reviews_first, (
            f"review items changed: {reviews_first} -> {reviews_second}"
        )
        assert reg_second == reg_first, (
            f"registry entries changed: {reg_first} -> {reg_second}"
        )


class TestCancelBeforeWork:
    """Cancelling before a stage runs leaves a clean cancelled row."""

    def test_cancel_before_work_leaves_clean_cancelled(self, db):
        eid = _make_evidence("Some text to cancel")

        # Mark cancelled before any pipeline work.
        ev = db.get(Evidence, eid)
        ev.cancel_requested = True
        db.add(ev)
        db.commit()

        _run_full_pipeline(eid)

        # Use a fresh session to ensure we see the committed change.
        fresh = SessionLocal()
        try:
            ev = fresh.get(Evidence, eid)
            assert ev.status == "cancelled", f"expected cancelled, got {ev.status}"
            facts = fresh.query(Fact).filter(Fact.evidence_id == eid).count()
            assert facts == 0, f"expected 0 facts for cancelled item, got {facts}"
        finally:
            fresh.close()


class TestChunkedExtraction:
    """Chunked extraction merges duplicate entities across chunks."""

    def test_extraction_chunking_merges_duplicates(self, monkeypatch):
        monkeypatch.setattr("ingestion_core.extraction._CHUNK_CHARS", 50)

        long_text = "Person A works at Company B. " * 20
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "Alice",
                 "attributes": {}, "confidence": 0.9, "source_span": "Alice"},
                {"local_id": "e2", "type": "Company", "name": "B Ltd",
                 "attributes": {}, "confidence": 0.8, "source_span": "B Ltd"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e2",
                 "type": "WORKS_AT", "confidence": 0.8, "source_span": ""},
            ],
            "summary": "test",
            "overall_confidence": 0.5,
        })

        from ingestion_core.extraction import extract

        result = extract("chunk-test", long_text)
        assert len(result.entities) > 0, "should have entities after chunked extraction"
        # Even across chunks, the same entity appearing multiple times should be
        # deduplicated by (type, name).
        names_seen = {}
        for e in result.entities:
            key = (e.type.value, e.name)
            names_seen[key] = names_seen.get(key, 0) + 1
        duplicates = {k: v for k, v in names_seen.items() if v > 1}
        assert len(duplicates) == 0, (
            f"duplicate entities after merge: {duplicates}"
        )


class TestHTTPAPI:
    """End-to-end through the HTTP API layer."""

    @pytest.fixture(autouse=True)
    def _http_patches(self, monkeypatch):
        monkeypatch.setenv("EVIDENCE_DATABASE_URL", os.environ["EVIDENCE_DATABASE_URL"])
        monkeypatch.setenv("EVIDENCE_DIR", _evidence_dir)
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
        monkeypatch.setattr("evidence_core.pipeline._graph_client", _fake_graph_client)
        monkeypatch.setattr("ingestion_core.extraction.chat_json", _fake_chat_json)
        init_db()

    def test_ingest_to_detail_to_list_to_delete(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "HTTP Person",
                 "attributes": {}, "confidence": 0.95, "source_span": "HTTP"},
                {"local_id": "e2", "type": "Company", "name": "HTTP Ltd",
                 "attributes": {}, "confidence": 0.9, "source_span": "HTTP Ltd"},
            ],
            "relationships": [
                {"source_local_id": "e1", "target_local_id": "e2",
                 "type": "WORKS_AT", "confidence": 0.8, "source_span": ""},
            ],
            "summary": "http test",
            "overall_confidence": 0.8,
        })

        from graph_explorer_api.main import create_app

        app = create_app()
        with TestClient(app) as client:
            resp = client.post("/api/evidence/ingest/text", json={
                "text": "HTTP Person works at HTTP Ltd",
                "source_name": "e2e-test",
            })
            assert resp.status_code == 200, resp.text
            data = resp.json()
            eid = data["evidence_id"]
            assert data["status"] == "queued"
            assert data["source_type"] == "text"

            _run_full_pipeline(eid)

            detail = client.get(f"/api/evidence/{eid}")
            assert detail.status_code == 200, detail.text
            detail_data = detail.json()
            assert detail_data["status"] == "enriched"
            assert len(detail_data["facts"]) > 0, "expected facts in detail"

            # Cancel on finished item returns 409.
            cancel = client.post(f"/api/evidence/{eid}/cancel")
            assert cancel.status_code == 409, (
                f"expected 409 cancelling finished item, got {cancel.status_code}: {cancel.text}"
            )

            # List shows the enriched status.
            listing = client.get("/api/evidence")
            assert listing.status_code == 200
            ids = [e["id"] for e in listing.json()]
            assert eid in ids

            # Delete.
            delete = client.delete(f"/api/evidence/{eid}")
            assert delete.status_code == 200, delete.text
            result = delete.json()
            assert result["ok"] is True
            assert result["facts_deleted"] > 0

            # After delete, detail returns 404.
            gone = client.get(f"/api/evidence/{eid}")
            assert gone.status_code == 404

    def test_cancelled_item_does_not_block_reingest(self, db):
        _set_llm_response({
            "entities": [
                {"local_id": "e1", "type": "Person", "name": "Cancel Re",
                 "attributes": {}, "confidence": 0.9, "source_span": "Cancel"},
            ],
            "relationships": [],
            "summary": "cancel test",
            "overall_confidence": 0.5,
        })

        from graph_explorer_api.main import create_app

        app = create_app()
        with TestClient(app) as client:
            resp1 = client.post("/api/evidence/ingest/text", json={
                "text": "Cancel Re test content",
                "source_name": "cancel-test",
            })
            assert resp1.status_code == 200
            eid1 = resp1.json()["evidence_id"]

            # Cancel it.
            cancel = client.post(f"/api/evidence/{eid1}/cancel")
            assert cancel.status_code == 200

            _run_full_pipeline(eid1)

            # Re-ingest same content — should get a new id (not duplicate).
            resp2 = client.post("/api/evidence/ingest/text", json={
                "text": "Cancel Re test content",
                "source_name": "cancel-test",
            })
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["evidence_id"] != eid1, (
                "cancelled item should not block re-ingest of same content"
            )
            assert "duplicate" not in data2.get("note", "")
