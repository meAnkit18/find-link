from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from evidence_core.database import SessionLocal
from evidence_core.db_models import EntityRegistry, Evidence, Fact, ReviewItem, utcnow
from graph_explorer_api.config import Settings
from graph_explorer_api.dependencies import get_settings
from graph_explorer_api.graph_clients import GraphClientCache
from ingestion_core.parsers.detect import detect_source_type
from intelligence_schema.graph_writer import GraphWriter

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TextIn(BaseModel):
    text: str
    source_name: str = "manual-text"
    uploaded_by: str = "anonymous"


@router.post("/ingest/text")
def ingest_text(body: TextIn, db: Session = Depends(get_db)):  # noqa: B008
    sha256 = hashlib.sha256(body.text.encode()).hexdigest()
    existing = db.query(Evidence).filter(
        Evidence.sha256 == sha256,
        Evidence.status != "failed",
    ).first()
    if existing:
        return {"evidence_id": existing.id, "status": existing.status, "note": "duplicate"}

    ev = Evidence(
        source_name=body.source_name,
        source_type="text",
        sha256=sha256,
        raw_text=body.text,
        uploaded_by=body.uploaded_by,
    )
    db.add(ev)
    db.commit()

    _dispatch_pipeline(ev.id)
    return {"evidence_id": ev.id, "status": "queued", "source_type": "text"}


@router.post("/ingest/file")
def ingest_file(
    file: UploadFile = File(...),  # noqa: B008
    uploaded_by: str = Form("anonymous"),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    try:
        source_type = detect_source_type(file.filename)
    except ValueError as e:
        raise HTTPException(415, str(e)) from e

    data = file.file.read()
    sha256 = hashlib.sha256(data).hexdigest()

    existing = db.query(Evidence).filter(
        Evidence.sha256 == sha256,
        Evidence.status != "failed",
    ).first()
    if existing:
        return {"evidence_id": existing.id, "status": existing.status, "note": "duplicate"}

    ev = Evidence(
        source_name=file.filename,
        source_type=source_type,
        sha256=sha256,
        uploaded_by=uploaded_by,
    )
    db.add(ev)
    db.flush()

    dest = Path(settings.evidence_dir) / f"{ev.id}_{file.filename}"
    with open(dest, "wb") as fh:
        fh.write(data)
    ev.stored_path = str(dest)
    db.commit()

    _dispatch_pipeline(ev.id)
    return {"evidence_id": ev.id, "status": "queued", "source_type": source_type}


@router.get("/{evidence_id}")
def get_evidence(evidence_id: str, db: Session = Depends(get_db)):  # noqa: B008
    ev = db.get(Evidence, evidence_id)
    if not ev:
        raise HTTPException(404, "unknown evidence id")
    facts = db.query(Fact).filter(Fact.evidence_id == evidence_id).all()
    return {
        "id": ev.id,
        "source_name": ev.source_name,
        "source_type": ev.source_type,
        "sha256": ev.sha256,
        "uploaded_by": ev.uploaded_by,
        "uploaded_at": ev.uploaded_at,
        "status": ev.status,
        "error": ev.error,
        "processing_log": ev.processing_log,
        "extraction": ev.extraction_json,
        "facts": [
            {"id": f.id, "kind": f.kind, "status": f.status,
             "origin": f.origin, "confidence": f.confidence,
             "payload": f.payload}
            for f in facts
        ],
    }


@router.get("/review/queue")
def review_queue(state: str = "open", db: Session = Depends(get_db)):  # noqa: B008
    items = (
        db.query(ReviewItem)
        .filter(ReviewItem.state == state)
        .order_by(ReviewItem.created_at)
        .limit(200)
        .all()
    )
    return [
        {"id": r.id, "fact_id": r.fact_id, "evidence_id": r.evidence_id,
         "reason": r.reason, "detail": r.detail, "created_at": r.created_at}
        for r in items
    ]


@router.post("/review/{item_id}/approve")
def approve_review(
    item_id: int,
    decided_by: str = "reviewer",
    db: Session = Depends(get_db),  # noqa: B008
    request: Request = None,
):
    item = db.get(ReviewItem, item_id)
    if not item or item.state != "open":
        raise HTTPException(404, "no open review item with that id")
    fact = db.get(Fact, item.fact_id)

    if request is not None:
        clients: GraphClientCache = request.app.state.clients
        client = clients.for_space("intelligence_graph")
    else:
        from graph_core.client import GraphClient
        from graph_core.config import GraphConfig
        client = GraphClient(GraphConfig(
            hosts=["127.0.0.1:9669"],
            user="root", password="nebula",
            space="intelligence_graph",
        ))
        client.connect()

    writer = GraphWriter(client)

    try:
        if fact.kind == "entity":
            reg = db.get(EntityRegistry, fact.resolved_entity_id)
            if reg:
                writer.upsert_entity(
                    tag=reg.type, vid=reg.id, name=reg.canonical_name,
                    attributes={**(reg.attributes or {}), "aliases": reg.aliases or []},
                    confidence=reg.confidence, evidence_id=fact.evidence_id,
                )
                writer.link_supported_by(reg.id, fact.evidence_id, fact.confidence)
        else:
            p = fact.payload
            writer.upsert_relationship(
                edge_type=p["type"], src_id=fact.resolved_source_id,
                dst_id=fact.resolved_target_id, confidence=fact.confidence,
                status="accepted", evidence_id=fact.evidence_id,
                attributes=p.get("attributes"),
                relation_label=p.get("relation_label"),
            )

        fact.status = "written"
        item.state, item.decided_by, item.decided_at = "approved", decided_by, utcnow()
        db.add_all([fact, item])
        db.commit()
    finally:
        if request is None:
            client.close()

    return {"ok": True, "fact_id": fact.id}


@router.post("/review/{item_id}/reject")
def reject_review(item_id: int, decided_by: str = "reviewer", db: Session = Depends(get_db)):  # noqa: B008
    item = db.get(ReviewItem, item_id)
    if not item or item.state != "open":
        raise HTTPException(404, "no open review item with that id")
    fact = db.get(Fact, item.fact_id)
    fact.status = "rejected"
    item.state, item.decided_by, item.decided_at = "rejected", decided_by, utcnow()
    db.add_all([fact, item])
    db.commit()
    return {"ok": True}


@router.get("/entities/list")
def list_entities(
    type: str | None = None,
    q: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),  # noqa: B008
):
    query = db.query(EntityRegistry)
    if type:
        query = query.filter(EntityRegistry.type == type)
    if q:
        query = query.filter(EntityRegistry.canonical_name.ilike(f"%{q}%"))
    rows = query.order_by(EntityRegistry.updated_at.desc()).limit(limit).all()
    return [
        {"id": r.id, "type": r.type, "name": r.canonical_name,
         "aliases": r.aliases, "attributes": r.attributes,
         "confidence": r.confidence,
         "evidence_count": len(r.evidence_ids or [])}
        for r in rows
    ]


def _dispatch_pipeline(evidence_id: str) -> None:
    try:
        from worker.pipeline import run_pipeline
        run_pipeline(evidence_id)
    except ImportError:
        pass
