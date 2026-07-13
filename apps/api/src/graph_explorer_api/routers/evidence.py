from __future__ import annotations

import hashlib
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from evidence_core.database import SessionLocal
from evidence_core.db_models import EntityRegistry, Evidence, Fact, ReviewItem, utcnow
from evidence_core.pipeline import run_pipeline_inline
from graph_explorer_api.config import Settings
from graph_explorer_api.dependencies import get_settings
from graph_explorer_api.graph_clients import GraphClientCache
from ingestion_core.parsers.detect import detect_source_type
from intelligence_schema.graph_writer import GraphWriter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

INTEL_GRAPH_NAME = "Intelligence Graph"

# Statuses where the pipeline is (or may still be) running.
ACTIVE_STATUSES = {"uploaded", "queued", "parsed", "extracted", "resolved", "written"}
# Statuses where the pipeline is definitively finished.
TERMINAL_STATUSES = {"enriched", "failed", "cancelled"}

_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.environ.get("INGEST_WORKERS", "2")),
    thread_name_prefix="ingest",
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name[:200] or "upload"


# ------------------------------------------------------------------ dispatch

def _dispatch_pipeline(evidence_id: str, request: Request) -> None:
    settings: Settings = request.app.state.settings

    if settings.ingest_mode == "celery":
        try:
            from worker.pipeline import run_pipeline
            run_pipeline(evidence_id)
        except Exception as exc:
            _mark_failed(evidence_id, f"celery dispatch: {exc}")
            raise HTTPException(
                503,
                "INGEST_MODE=celery but the Celery pipeline is unavailable "
                f"({exc}). Start Redis + a worker, or set INGEST_MODE=inline.",
            ) from exc
        return

    app = request.app
    space = settings.nebula_space

    def _after_write(counts: tuple[int, int]) -> None:
        app.state.search_index.invalidate(space)
        app.state.registry.ensure(space, INTEL_GRAPH_NAME)
        app.state.registry.add_stats(space, counts[0], counts[1])

    def _run() -> None:
        try:
            run_pipeline_inline(evidence_id, on_written=_after_write)
        except Exception:
            logger.exception("ingest pipeline failed for evidence %s", evidence_id)

    _EXECUTOR.submit(_run)


def _mark_failed(evidence_id: str, error: str) -> None:
    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        if ev is not None:
            ev.status = "failed"
            ev.error = error
            db.add(ev)
            db.commit()
    finally:
        db.close()


# ------------------------------------------------------------------- ingest

class TextIn(BaseModel):
    text: str
    source_name: str = "manual-text"
    uploaded_by: str = "anonymous"


@router.post("/ingest/text")
def ingest_text(body: TextIn, request: Request, db: Session = Depends(get_db)):  # noqa: B008
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text must not be empty")

    sha256 = hashlib.sha256(text.encode()).hexdigest()
    existing = db.query(Evidence).filter(
        Evidence.sha256 == sha256,
        Evidence.status.notin_(["failed", "cancelled"]),
    ).first()
    if existing:
        return {"evidence_id": existing.id, "status": existing.status, "note": "duplicate"}

    ev = Evidence(
        source_name=body.source_name,
        source_type="text",
        sha256=sha256,
        raw_text=text,
        uploaded_by=body.uploaded_by,
    )
    db.add(ev)
    db.commit()

    _dispatch_pipeline(ev.id, request)
    return {"evidence_id": ev.id, "status": "queued", "source_type": "text"}


@router.post("/ingest/file")
def ingest_file(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    uploaded_by: str = Form("anonymous"),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    safe_name = _safe_filename(file.filename)
    try:
        source_type = detect_source_type(safe_name)
    except ValueError as e:
        raise HTTPException(415, str(e)) from e

    data = file.file.read()
    if not data:
        raise HTTPException(422, "uploaded file is empty")
    sha256 = hashlib.sha256(data).hexdigest()

    existing = db.query(Evidence).filter(
        Evidence.sha256 == sha256,
        Evidence.status.notin_(["failed", "cancelled"]),
    ).first()
    if existing:
        return {"evidence_id": existing.id, "status": existing.status, "note": "duplicate"}

    ev = Evidence(
        source_name=safe_name,
        source_type=source_type,
        sha256=sha256,
        uploaded_by=uploaded_by,
    )
    db.add(ev)
    db.flush()

    dest = (Path(settings.evidence_dir) / f"{ev.id}_{safe_name}").resolve()
    if not str(dest).startswith(str(Path(settings.evidence_dir).resolve())):
        raise HTTPException(400, "invalid filename")
    with open(dest, "wb") as fh:
        fh.write(data)
    ev.stored_path = str(dest)
    db.commit()

    _dispatch_pipeline(ev.id, request)
    return {"evidence_id": ev.id, "status": "queued", "source_type": source_type}


# ------------------------------------------------------------------ listing

@router.get("")
def list_evidence(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),  # noqa: B008
):
    query = db.query(Evidence)
    if status:
        query = query.filter(Evidence.status == status)
    rows = query.order_by(Evidence.uploaded_at.desc()).limit(min(limit, 200)).all()
    return [
        {
            "id": ev.id,
            "source_name": ev.source_name,
            "source_type": ev.source_type,
            "status": ev.status,
            "cancel_requested": bool(ev.cancel_requested),
            "uploaded_at": ev.uploaded_at,
            "error": ev.error,
            # last processing_log entry → lets the list show live internal
            # activity without the client fetching every detail record
            "last_log": (ev.processing_log or [None])[-1],
        }
        for ev in rows
    ]


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
        "cancel_requested": bool(ev.cancel_requested),
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


@router.post("/{evidence_id}/retry")
def retry_evidence(evidence_id: str, request: Request, db: Session = Depends(get_db)):  # noqa: B008
    ev = db.get(Evidence, evidence_id)
    if not ev:
        raise HTTPException(404, "unknown evidence id")
    if ev.status not in ("failed", "cancelled"):
        raise HTTPException(
            409,
            f"evidence is '{ev.status}', only failed or cancelled items can be retried",
        )
    ev.status = "uploaded"
    ev.error = None
    ev.cancel_requested = False
    log = list(ev.processing_log or [])
    log.append({"stage": "retry", "at": utcnow().isoformat(),
                "detail": "pipeline restarted by user"})
    ev.processing_log = log
    db.add(ev)
    db.commit()
    _dispatch_pipeline(evidence_id, request)
    return {"evidence_id": evidence_id, "status": "queued"}


@router.post("/{evidence_id}/cancel")
def cancel_evidence(evidence_id: str, db: Session = Depends(get_db)):  # noqa: B008
    """Ask the pipeline to stop this evidence.

    The flag is checked at every stage boundary, so a running stage finishes
    its own work and the item then flips to `cancelled`. Items still waiting
    in the queue are cancelled the moment they would have started.
    """
    ev = db.get(Evidence, evidence_id)
    if not ev:
        raise HTTPException(404, "unknown evidence id")
    if ev.status in TERMINAL_STATUSES:
        raise HTTPException(409, f"evidence already finished with status '{ev.status}'")
    if not ev.cancel_requested:
        ev.cancel_requested = True
        log = list(ev.processing_log or [])
        log.append({"stage": "cancel", "at": utcnow().isoformat(),
                    "detail": "stop requested by user — will halt at the next stage boundary"})
        ev.processing_log = log
        db.add(ev)
        db.commit()
    return {"evidence_id": evidence_id, "status": ev.status, "cancel_requested": True}


@router.delete("/{evidence_id}")
def delete_evidence(
    evidence_id: str,
    request: Request,
    force: bool = False,
    db: Session = Depends(get_db),  # noqa: B008
):
    """Delete an evidence item and everything derived from it.

    Removes: the evidence row, its stored file, its facts and review items,
    its id from every EntityRegistry row (deleting registry entries that
    were supported *only* by this evidence), and — best effort — its
    evidence vertex and orphaned entity vertices in the graph.

    If the pipeline is still running, refuse unless ?force=true, in which
    case the cancel flag is set so any in-flight step stops safely (steps
    treat a deleted row as a cancellation).
    """
    ev = db.get(Evidence, evidence_id)
    if not ev:
        raise HTTPException(404, "unknown evidence id")
    if ev.status in ACTIVE_STATUSES and not force:
        raise HTTPException(
            409,
            "pipeline is still running — press Stop first (or call this "
            "endpoint with ?force=true)",
        )
    if ev.status in ACTIVE_STATUSES:
        ev.cancel_requested = True
        db.add(ev)
        db.commit()

    # 1) collect the registry entities this evidence touched
    facts = db.query(Fact).filter(Fact.evidence_id == evidence_id).all()
    touched_entity_ids: set[str] = set()
    for f in facts:
        for eid in (f.resolved_entity_id, f.resolved_source_id, f.resolved_target_id):
            if eid:
                touched_entity_ids.add(eid)

    # 2) delete review items + facts
    review_deleted = (
        db.query(ReviewItem)
        .filter(ReviewItem.evidence_id == evidence_id)
        .delete(synchronize_session=False)
    )
    facts_deleted = (
        db.query(Fact)
        .filter(Fact.evidence_id == evidence_id)
        .delete(synchronize_session=False)
    )

    # 3) scrub this evidence id from the registry; drop entities that were
    #    supported only by this evidence
    orphaned_registry_ids: list[str] = []
    for eid in touched_entity_ids:
        reg = db.get(EntityRegistry, eid)
        if reg is None:
            continue
        remaining = [x for x in (reg.evidence_ids or []) if x != evidence_id]
        if remaining:
            reg.evidence_ids = remaining
            db.add(reg)
        else:
            orphaned_registry_ids.append(reg.id)
            db.delete(reg)

    # 4) delete the stored file (if any)
    if ev.stored_path:
        try:
            Path(ev.stored_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("could not delete stored file %s", ev.stored_path)

    # 5) delete the evidence row itself
    db.delete(ev)
    db.commit()

    # 6) best-effort graph cleanup (never fails the request)
    graph_cleaned = False
    try:
        settings: Settings = request.app.state.settings
        clients: GraphClientCache = request.app.state.clients
        client = clients.for_space(settings.nebula_space)
        client.execute_raw(f'DELETE VERTEX "{evidence_id}" WITH EDGE')
        for eid in orphaned_registry_ids:
            client.execute_raw(f'DELETE VERTEX "{eid}" WITH EDGE')
        request.app.state.search_index.invalidate(settings.nebula_space)
        graph_cleaned = True
    except Exception:
        logger.exception("graph cleanup for evidence %s failed (non-fatal)", evidence_id)

    return {
        "ok": True,
        "evidence_id": evidence_id,
        "facts_deleted": facts_deleted,
        "review_items_deleted": review_deleted,
        "registry_entities_deleted": len(orphaned_registry_ids),
        "graph_cleaned": graph_cleaned,
    }


# ------------------------------------------------------------- review queue

@router.get("/review/queue")
def review_queue(state: str = "open", db: Session = Depends(get_db)):  # noqa: B008
    items = (
        db.query(ReviewItem)
        .filter(ReviewItem.state == state)
        .order_by(ReviewItem.created_at)
        .limit(200)
        .all()
    )
    out = []
    for r in items:
        fact = db.get(Fact, r.fact_id)
        out.append({
            "id": r.id, "fact_id": r.fact_id, "evidence_id": r.evidence_id,
            "reason": r.reason, "detail": r.detail, "created_at": r.created_at,
            "kind": fact.kind if fact else None,
        })
    return out


@router.post("/review/{item_id}/approve")
def approve_review(
    item_id: int,
    request: Request,
    decided_by: str = "reviewer",
    db: Session = Depends(get_db),  # noqa: B008
):
    item = db.get(ReviewItem, item_id)
    if not item or item.state != "open":
        raise HTTPException(404, "no open review item with that id")
    fact = db.get(Fact, item.fact_id)
    if fact is None:
        raise HTTPException(404, "fact for this review item no longer exists")

    settings: Settings = request.app.state.settings
    clients: GraphClientCache = request.app.state.clients
    client = clients.for_space(settings.nebula_space)
    writer = GraphWriter(client)

    if fact.kind == "entity":
        reg = db.get(EntityRegistry, fact.resolved_entity_id)
        if reg:
            writer.upsert_entity(
                tag=reg.type, vid=reg.id, name=reg.canonical_name,
                attributes={**(reg.attributes or {}), "aliases": reg.aliases or []},
                confidence=reg.confidence, evidence_id=fact.evidence_id,
            )
            writer.link_supported_by(reg.id, fact.evidence_id, fact.confidence)
    elif fact.kind == "merge_suggestion":
        p = fact.payload or {}
        new_reg = db.get(EntityRegistry, p.get("new_entity_id"))
        cand_reg = db.get(EntityRegistry, p.get("candidate_entity_id"))
        if new_reg and cand_reg:
            aliases = set(cand_reg.aliases or [])
            aliases.add(new_reg.canonical_name)
            aliases.update(new_reg.aliases or [])
            cand_reg.aliases = sorted(a for a in aliases if a != cand_reg.canonical_name)
            ev_ids = set(cand_reg.evidence_ids or []) | set(new_reg.evidence_ids or [])
            cand_reg.evidence_ids = sorted(ev_ids)
            db.add(cand_reg)
            writer.upsert_relationship(
                edge_type="RELATED_TO",
                src_id=new_reg.id, dst_id=cand_reg.id,
                confidence=fact.confidence, status="accepted",
                evidence_id=fact.evidence_id,
                relation_label="same_as",
            )
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

    request.app.state.search_index.invalidate(settings.nebula_space)

    return {"ok": True, "fact_id": fact.id}


@router.post("/review/{item_id}/reject")
def reject_review(item_id: int, decided_by: str = "reviewer", db: Session = Depends(get_db)):  # noqa: B008
    item = db.get(ReviewItem, item_id)
    if not item or item.state != "open":
        raise HTTPException(404, "no open review item with that id")
    fact = db.get(Fact, item.fact_id)
    if fact is not None:
        fact.status = "rejected"
        db.add(fact)
    item.state, item.decided_by, item.decided_at = "rejected", decided_by, utcnow()
    db.add(item)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- entities

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
