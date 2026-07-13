from __future__ import annotations

import os

from celery import Celery, chain
from sqlalchemy.orm import Session

from evidence_core.config import get_settings as get_evidence_settings
from evidence_core.database import SessionLocal, init_db
from evidence_core.db_models import EntityRegistry, Evidence, Fact, ReviewItem, utcnow
from ingestion_core import extraction as ex
from ingestion_core.canonical import ExtractionResult
from ingestion_core.normalize import normalize_extraction
from ingestion_core.parsers.detect import get_parser

celery_app = Celery(
    "kgpipeline",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

init_db()


def _log(ev: Evidence, stage: str, detail: str) -> None:
    log = list(ev.processing_log or [])
    log.append({"stage": stage, "at": utcnow().isoformat(), "detail": detail})
    ev.processing_log = log


def _fail(db: Session, ev: Evidence, stage: str, exc: Exception) -> None:
    ev.status = "failed"
    ev.error = f"{stage}: {exc}"
    _log(ev, stage, f"FAILED: {exc}")
    db.add(ev)
    db.commit()


@celery_app.task(name="pipeline.parse", bind=True, max_retries=2)
def parse_task(self, evidence_id: str) -> str:
    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        if ev.source_type == "text":
            raw = ev.raw_text or ""
            hint = "Raw text input."
        else:
            parser = get_parser(ev.source_type)
            out = parser.parse(ev.stored_path)
            raw, hint = out.text, out.structured_hint
        ev.raw_text = raw
        ev.status = "parsed"
        log = dict(ev.extraction_json or {})
        log["structured_hint"] = hint
        ev.extraction_json = log
        _log(ev, "parse", f"{len(raw)} chars extracted")
        db.add(ev)
        db.commit()
        return evidence_id
    except Exception as exc:
        _fail(db, db.get(Evidence, evidence_id), "parse", exc)
        raise
    finally:
        db.close()


@celery_app.task(name="pipeline.extract", bind=True, max_retries=2, default_retry_delay=30)
def extract_task(self, evidence_id: str) -> str:
    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        hint = (ev.extraction_json or {}).get("structured_hint", "")
        result = ex.extract(evidence_id, ev.raw_text or "", hint)
        result = normalize_extraction(result)
        ev.extraction_json = result.model_dump(mode="json")
        ev.status = "extracted"
        _log(ev, "extract",
             f"{len(result.entities)} entities, {len(result.relationships)} relationships")
        db.add(ev)
        db.commit()
        return evidence_id
    except Exception as exc:
        _fail(db, db.get(Evidence, evidence_id), "extract", exc)
        raise
    finally:
        db.close()


def _confidence_gate(fact: Fact, db: Session) -> None:
    settings = get_evidence_settings()
    if fact.confidence >= settings.conf_auto_accept:
        fact.status = "accepted"
    elif fact.confidence >= settings.conf_review_min:
        fact.status = "in_review"
        db.add(ReviewItem(
            fact_id=fact.id,
            evidence_id=fact.evidence_id,
            reason=f"confidence {fact.confidence:.2f} in review band",
            detail=fact.payload,
        ))
    else:
        fact.status = "rejected"
        db.add(ReviewItem(
            fact_id=fact.id,
            evidence_id=fact.evidence_id,
            reason=f"confidence {fact.confidence:.2f} below minimum",
            detail=fact.payload,
            state="rejected",
        ))
    db.add(fact)


@celery_app.task(name="pipeline.resolve", bind=True, max_retries=1)
def resolve_task(self, evidence_id: str) -> str:
    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        result = ExtractionResult(**ev.extraction_json)

        from ingestion_core.normalize import deterministic_key

        local_to_canonical: dict[str, str] = {}
        for mention in result.entities:
            det_key = deterministic_key(mention)
            entity_id = None
            if det_key:
                existing = (
                    db.query(EntityRegistry)
                    .filter(EntityRegistry.deterministic_key == det_key)
                    .first()
                )
                if existing:
                    entity_id = existing.id
                    aliases = set(existing.aliases or [])
                    if mention.name not in aliases:
                        aliases.add(mention.name)
                        existing.aliases = sorted(aliases)
                    ev_list = set(existing.evidence_ids or [])
                    ev_list.add(evidence_id)
                    existing.evidence_ids = sorted(ev_list)
                    existing.confidence = max(existing.confidence or 0.0, mention.confidence)
                    db.add(existing)

            if entity_id is None:
                reg = EntityRegistry(
                    type=mention.type.value,
                    canonical_name=mention.name,
                    deterministic_key=det_key,
                    aliases=[],
                    attributes=dict(mention.attributes),
                    confidence=mention.confidence,
                    evidence_ids=[evidence_id],
                )
                db.add(reg)
                db.flush()
                entity_id = reg.id

            local_to_canonical[mention.local_id] = entity_id
            fact = Fact(
                evidence_id=evidence_id,
                kind="entity",
                payload=mention.model_dump(mode="json"),
                resolved_entity_id=entity_id,
                confidence=mention.confidence,
            )
            _confidence_gate(fact, db)

        for rel in result.relationships:
            src = local_to_canonical.get(rel.source_local_id)
            tgt = local_to_canonical.get(rel.target_local_id)
            if not src or not tgt:
                continue
            fact = Fact(
                evidence_id=evidence_id,
                kind="relationship",
                payload=rel.model_dump(mode="json"),
                resolved_source_id=src,
                resolved_target_id=tgt,
                confidence=rel.confidence,
            )
            _confidence_gate(fact, db)

        ev.status = "resolved"
        _log(ev, "resolve", f"{len(local_to_canonical)} entities resolved")
        db.add(ev)
        db.commit()
        return evidence_id
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "resolve", exc)
        raise
    finally:
        db.close()


@celery_app.task(name="pipeline.write", bind=True, max_retries=3, default_retry_delay=15)
def write_task(self, evidence_id: str) -> str:
    from graph_core.client import GraphClient
    from graph_core.config import GraphConfig
    from intelligence_schema.graph_writer import GraphWriter

    client = GraphClient(GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user=os.environ.get("NEBULA_USER", "root"),
        password=os.environ.get("NEBULA_PASSWORD", "nebula"),
        space=os.environ.get("NEBULA_SPACE", "intelligence_graph"),
    ))
    client.connect()

    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        writer = GraphWriter(client)

        facts = db.query(Fact).filter(
            Fact.evidence_id == evidence_id,
            Fact.status == "accepted",
        ).all()
        written_entities: set[str] = set()

        for fact in (f for f in facts if f.kind == "entity"):
            reg = db.get(EntityRegistry, fact.resolved_entity_id)
            if reg:
                writer.upsert_entity(
                    tag=reg.type,
                    vid=reg.id,
                    name=reg.canonical_name,
                    attributes={**(reg.attributes or {}), "aliases": reg.aliases or []},
                    confidence=reg.confidence,
                    evidence_id=evidence_id,
                )
                writer.link_supported_by(reg.id, evidence_id, fact.confidence)
                written_entities.add(reg.id)
                fact.status = "written"
                db.add(fact)

        for fact in (f for f in facts if f.kind == "relationship"):
            p = fact.payload
            status = "proposed" if fact.origin == "enrichment" else "accepted"
            writer.upsert_relationship(
                edge_type=p["type"],
                src_id=fact.resolved_source_id,
                dst_id=fact.resolved_target_id,
                confidence=fact.confidence,
                status=status,
                evidence_id=evidence_id,
                attributes=p.get("attributes"),
                relation_label=p.get("relation_label"),
            )
            fact.status = "written"
            db.add(fact)

        ev.status = "written"
        _log(ev, "write", f"{len(facts)} facts projected to NebulaGraph")
        db.add(ev)
        db.commit()
        client.close()
        return f"{evidence_id}|{','.join(sorted(written_entities))}"
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "write", exc)
        client.close()
        raise
    finally:
        db.close()


@celery_app.task(name="pipeline.enrich", bind=True, max_retries=1)
def enrich_task(self, handoff: str) -> str:
    evidence_id, _, id_csv = handoff.partition("|")
    entity_ids = [i for i in id_csv.split(",") if i]
    if not entity_ids:
        return evidence_id

    from graph_core.client import GraphClient
    from graph_core.config import GraphConfig
    from intelligence_schema.graph_writer import GraphWriter
    from reasoning_core.enrichment import enrich

    client = GraphClient(GraphConfig(
        hosts=[("127.0.0.1", 9669)],
        user=os.environ.get("NEBULA_USER", "root"),
        password=os.environ.get("NEBULA_PASSWORD", "nebula"),
        space=os.environ.get("NEBULA_SPACE", "intelligence_graph"),
    ))
    client.connect()

    db = SessionLocal()
    try:
        ev = db.get(Evidence, evidence_id)
        writer = GraphWriter(client)
        n = enrich(db, evidence_id, entity_ids, writer.fetch_neighborhood)

        accepted = db.query(Fact).filter(
            Fact.evidence_id == evidence_id,
            Fact.origin == "enrichment",
            Fact.status == "accepted",
        ).all()
        for fact in accepted:
            p = fact.payload
            writer.upsert_relationship(
                edge_type=p["type"],
                src_id=fact.resolved_source_id,
                dst_id=fact.resolved_target_id,
                confidence=fact.confidence,
                status="proposed",
                evidence_id=evidence_id,
                attributes=p.get("attributes"),
                relation_label=p.get("relation_label"),
            )
            fact.status = "written"
            db.add(fact)

        ev.status = "enriched"
        _log(ev, "enrich", f"{n} inference proposals generated")
        db.add(ev)
        db.commit()
        client.close()
        return evidence_id
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "enrich", exc)
        client.close()
        raise
    finally:
        db.close()


def run_pipeline(evidence_id: str) -> None:
    chain(
        parse_task.s(evidence_id),
        extract_task.s(),
        resolve_task.s(),
        write_task.s(),
        enrich_task.s(),
    ).apply_async()
