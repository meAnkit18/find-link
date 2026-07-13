"""Evidence pipeline steps: parse -> extract -> resolve -> write -> enrich.

These are plain functions (no Celery imports) so they can run either:
  - inline, in a background thread inside the API process (INGEST_MODE=inline), or
  - as Celery tasks (apps/worker/src/worker/pipeline.py wraps them).

Each step loads the Evidence row, does its work, commits, and updates
Evidence.status. On failure the step marks the evidence `failed` with the
stage and error, then re-raises (so Celery retries still work and the inline
runner stops the chain).

Cancellation
------------
Users can request a stop (`Evidence.cancel_requested = True`, set by
POST /api/evidence/{id}/cancel). Every step checks the flag before doing any
work; if it is set — or the evidence row has been deleted — the step raises
PipelineCancelled, marks the row `cancelled`, and the chain stops. A step
that is already mid-flight finishes its own work, so cancellation takes
effect at the next stage boundary (at most a few seconds for everything
except a slow LLM extraction call).

Observability
-------------
Every step now appends BOTH a "started" and a "finished (N.Ns)" entry to
Evidence.processing_log, so the UI can stream exactly what the pipeline is
doing in real time, including per-stage durations.

Entity resolution here is what makes repeated ingestion *enrich* the graph
instead of duplicating it:
  1. deterministic keys (normalized email/phone/passport/IBAN/plate/ISO2)
  2. fuzzy name matching (rapidfuzz token_sort_ratio) against canonical
     names AND aliases of same-type entities in the registry
       score >= ER_FUZZY_AUTO      -> merge into the existing entity
       score >= ER_FUZZY_CANDIDATE -> create, but open a merge-suggestion
                                      review item so a human can link them
      otherwise                   -> create a new entity
"""

from __future__ import annotations

import os
import time
from typing import Callable

from sqlalchemy.orm import Session

from evidence_core.config import get_settings
from evidence_core.database import SessionLocal, init_db
from evidence_core.db_models import EntityRegistry, Evidence, Fact, ReviewItem, utcnow


class PipelineCancelled(Exception):
    """Raised when the user asked to stop this evidence, or deleted it."""


# --------------------------------------------------------------------------- helpers

def _log(ev: Evidence, stage: str, detail: str) -> None:
    log = list(ev.processing_log or [])
    log.append({"stage": stage, "at": utcnow().isoformat(), "detail": detail})
    ev.processing_log = log


def _fail(db: Session, ev: Evidence | None, stage: str, exc: Exception) -> None:
    if ev is None:
        return
    ev.status = "failed"
    ev.error = f"{stage}: {exc}"
    _log(ev, stage, f"FAILED: {exc}")
    db.add(ev)
    db.commit()


def _load_checked(db: Session, evidence_id: str, stage: str) -> Evidence:
    """Load the evidence row, honouring cancellation / deletion.

    Raises PipelineCancelled if the row is gone (deleted while queued/running)
    or the user requested a stop. In the cancel case the row is marked
    `cancelled` and the request is committed before raising.
    """
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise PipelineCancelled(f"{stage}: evidence row was deleted")
    if ev.cancel_requested:
        ev.status = "cancelled"
        _log(ev, stage, "stopped by user before this stage ran")
        db.add(ev)
        db.commit()
        raise PipelineCancelled(f"{stage}: stopped by user")
    return ev


def _graph_client():
    from graph_core.client import GraphClient
    from graph_core.config import GraphConfig

    config = GraphConfig(
        hosts=[(
            os.environ.get("NEBULA_HOST", "127.0.0.1"),
            int(os.environ.get("NEBULA_PORT", "9669")),
        )],
        user=os.environ.get("NEBULA_USER", "root"),
        password=os.environ.get("NEBULA_PASSWORD", "nebula"),
        space=os.environ.get("NEBULA_SPACE", "intelligence_graph"),
        use_ssl=os.environ.get("NEBULA_USE_SSL", "false").lower() == "true",
    )
    client = GraphClient(config)
    client.connect()
    return client


def _confidence_gate(fact: Fact, db: Session) -> None:
    settings = get_settings()
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


# --------------------------------------------------------------------------- step 1: parse

def step_parse(evidence_id: str) -> None:
    from ingestion_core.parsers.detect import get_parser

    db = SessionLocal()
    try:
        ev = _load_checked(db, evidence_id, "parse")
        _log(ev, "parse", f"started ({ev.source_type} source)")
        db.add(ev)
        db.commit()
        t0 = time.monotonic()

        if ev.source_type == "text":
            raw = ev.raw_text or ""
            hint = "Raw text input."
        else:
            parser = get_parser(ev.source_type)
            out = parser.parse(ev.stored_path)
            raw, hint = out.text, out.structured_hint
        if not raw.strip():
            raise ValueError(
                "no text could be extracted from this file "
                "(empty document, or OCR found nothing)"
            )
        ev.raw_text = raw
        ev.status = "parsed"
        meta = dict(ev.extraction_json or {})
        meta["structured_hint"] = hint
        ev.extraction_json = meta
        _log(ev, "parse", f"{len(raw)} chars extracted ({time.monotonic() - t0:.1f}s)")
        db.add(ev)
        db.commit()
    except PipelineCancelled:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "parse", exc)
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------- step 2: extract

def step_extract(evidence_id: str) -> None:
    from ingestion_core import extraction as ex
    from ingestion_core.normalize import normalize_extraction

    db = SessionLocal()
    try:
        ev = _load_checked(db, evidence_id, "extract")
        key = os.environ.get("LLM_API_KEY", "")
        if not key or key == "sk-not-set":
            raise RuntimeError(
                "LLM_API_KEY is not configured — set it in your environment/.env "
                "(the extraction step needs an OpenAI-compatible LLM endpoint)"
            )
        _log(ev, "extract", "started (calling LLM — this is the slow stage)")
        db.add(ev)
        db.commit()
        t0 = time.monotonic()

        hint = (ev.extraction_json or {}).get("structured_hint", "")
        result = ex.extract(evidence_id, ev.raw_text or "", hint)
        before = len(result.entities) + len(result.relationships)
        result = normalize_extraction(result)
        dropped = before - (len(result.entities) + len(result.relationships))
        ev.extraction_json = result.model_dump(mode="json")
        ev.status = "extracted"
        _log(
            ev, "extract",
            f"{len(result.entities)} entities, {len(result.relationships)} "
            f"relationships (dropped {dropped} invalid, "
            f"{time.monotonic() - t0:.1f}s)",
        )
        db.add(ev)
        db.commit()
    except PipelineCancelled:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "extract", exc)
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------- step 3: resolve

def _fuzzy_candidates(db: Session, mention) -> list[tuple[EntityRegistry, float]]:
    from rapidfuzz import fuzz

    rows = (
        db.query(EntityRegistry)
        .filter(EntityRegistry.type == mention.type.value)
        .limit(5000)
        .all()
    )
    name = mention.name.lower()
    scored: list[tuple[EntityRegistry, float]] = []
    for row in rows:
        best = fuzz.token_sort_ratio(name, (row.canonical_name or "").lower())
        for alias in row.aliases or []:
            best = max(best, fuzz.token_sort_ratio(name, str(alias).lower()))
        score = best / 100.0
        attrs = row.attributes or {}
        m_attrs = mention.attributes or {}
        if m_attrs.get("dob") and attrs.get("dob") == m_attrs.get("dob"):
            score = min(1.0, score + 0.07)
        if m_attrs.get("nationality") and attrs.get("nationality") == m_attrs.get("nationality"):
            score = min(1.0, score + 0.03)
        if score >= 0.5:
            scored.append((row, score))
    scored.sort(key=lambda t: -t[1])
    return scored[:5]


def _merge_into_registry(db: Session, existing: EntityRegistry, mention, evidence_id: str) -> None:
    aliases = set(existing.aliases or [])
    if mention.name != existing.canonical_name:
        aliases.add(mention.name)
    existing.aliases = sorted(aliases)
    merged_attrs = dict(existing.attributes or {})
    for k, v in (mention.attributes or {}).items():
        merged_attrs.setdefault(k, v)
    existing.attributes = merged_attrs
    ev_ids = set(existing.evidence_ids or [])
    ev_ids.add(evidence_id)
    existing.evidence_ids = sorted(ev_ids)
    existing.confidence = max(existing.confidence or 0.0, mention.confidence)
    db.add(existing)


def step_resolve(evidence_id: str) -> None:
    from ingestion_core.canonical import ExtractionResult
    from ingestion_core.normalize import deterministic_key

    fuzzy_auto = float(os.environ.get("ER_FUZZY_AUTO", "0.93"))
    fuzzy_candidate = float(os.environ.get("ER_FUZZY_CANDIDATE", "0.75"))

    db = SessionLocal()
    try:
        ev = _load_checked(db, evidence_id, "resolve")
        result = ExtractionResult(**(ev.extraction_json or {}))
        _log(
            ev, "resolve",
            f"started (matching {len(result.entities)} mentions against the registry)",
        )
        db.add(ev)
        db.commit()
        t0 = time.monotonic()

        local_to_canonical: dict[str, str] = {}
        merged, created, suggested = 0, 0, 0

        for mention in result.entities:
            entity_id: str | None = None
            method = "new"

            # 1) deterministic key
            det_key = deterministic_key(mention)
            if det_key:
                existing = (
                    db.query(EntityRegistry)
                    .filter(EntityRegistry.deterministic_key == det_key)
                    .first()
                )
                if existing:
                    _merge_into_registry(db, existing, mention, evidence_id)
                    entity_id, method = existing.id, "deterministic"

            # 2) fuzzy name/alias matching
            candidates: list[tuple[EntityRegistry, float]] = []
            if entity_id is None:
                candidates = _fuzzy_candidates(db, mention)
                if candidates and candidates[0][1] >= fuzzy_auto:
                    best = candidates[0][0]
                    _merge_into_registry(db, best, mention, evidence_id)
                    entity_id, method = best.id, f"fuzzy:{candidates[0][1]:.2f}"

            # 3) create a new canonical entity
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
                created += 1

                if candidates and candidates[0][1] >= fuzzy_candidate:
                    cand, score = candidates[0]
                    suggestion = Fact(
                        evidence_id=evidence_id,
                        kind="merge_suggestion",
                        payload={
                            "new_entity_id": entity_id,
                            "new_entity_name": mention.name,
                            "candidate_entity_id": cand.id,
                            "candidate_entity_name": cand.canonical_name,
                            "entity_type": mention.type.value,
                            "score": round(score, 3),
                        },
                        resolved_source_id=entity_id,
                        resolved_target_id=cand.id,
                        confidence=score,
                        status="in_review",
                    )
                    db.add(suggestion)
                    db.flush()
                    db.add(ReviewItem(
                        fact_id=suggestion.id,
                        evidence_id=evidence_id,
                        reason=(
                            f"possible duplicate: '{mention.name}' ~ "
                            f"'{cand.canonical_name}' ({score:.2f})"
                        ),
                        detail=suggestion.payload,
                    ))
                    suggested += 1
            else:
                merged += 1

            local_to_canonical[mention.local_id] = entity_id
            fact = Fact(
                evidence_id=evidence_id,
                kind="entity",
                payload=mention.model_dump(mode="json"),
                resolved_entity_id=entity_id,
                confidence=mention.confidence,
            )
            fact.payload["resolution_method"] = method
            _confidence_gate(fact, db)

        for rel in result.relationships:
            src = local_to_canonical.get(rel.source_local_id)
            tgt = local_to_canonical.get(rel.target_local_id)
            if not src or not tgt or src == tgt:
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
        _log(
            ev, "resolve",
            f"{merged} merged into existing entities, {created} created, "
            f"{suggested} merge suggestions queued "
            f"({time.monotonic() - t0:.1f}s)",
        )
        db.add(ev)
        db.commit()
    except PipelineCancelled:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "resolve", exc)
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------- step 4: write

def step_write(evidence_id: str) -> tuple[int, int]:
    from intelligence_schema.graph_writer import GraphWriter
    from intelligence_schema.ingest_schema import ensure_ingest_schema

    db = SessionLocal()
    client = None
    try:
        ev = _load_checked(db, evidence_id, "write")
        _log(ev, "write", "started (projecting accepted facts into the graph)")
        db.add(ev)
        db.commit()
        t0 = time.monotonic()

        client = _graph_client()
        space = os.environ.get("NEBULA_SPACE", "intelligence_graph")
        ensure_ingest_schema(client, space)

        writer = GraphWriter(client)

        writer.upsert_evidence(
            evidence_id=evidence_id,
            source_name=ev.source_name,
            source_type=ev.source_type,
        )

        facts = db.query(Fact).filter(
            Fact.evidence_id == evidence_id,
            Fact.status == "accepted",
        ).all()

        entities_written, edges_written = 0, 0

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
                entities_written += 1
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
            edges_written += 1
            fact.status = "written"
            db.add(fact)

        ev.status = "written"
        _log(
            ev, "write",
            f"{entities_written} entities, {edges_written} edges projected "
            f"({time.monotonic() - t0:.1f}s)",
        )
        db.add(ev)
        db.commit()
        return entities_written, edges_written
    except PipelineCancelled:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        _fail(db, db.get(Evidence, evidence_id), "write", exc)
        raise
    finally:
        db.close()
        if client is not None:
            client.close()


# --------------------------------------------------------------------------- step 5: enrich

def step_enrich(evidence_id: str) -> None:
    from intelligence_schema.graph_writer import GraphWriter
    from reasoning_core.enrichment import enrich

    db = SessionLocal()
    client = None
    try:
        ev = _load_checked(db, evidence_id, "enrich")

        entity_ids = sorted({
            f.resolved_entity_id
            for f in db.query(Fact).filter(
                Fact.evidence_id == evidence_id,
                Fact.kind == "entity",
                Fact.status == "written",
            )
            if f.resolved_entity_id
        })
        if not entity_ids:
            ev.status = "enriched"
            _log(ev, "enrich", "skipped (no written entities to enrich)")
            db.add(ev)
            db.commit()
            return

        _log(ev, "enrich", f"started (inferring around {len(entity_ids)} entities)")
        db.add(ev)
        db.commit()
        t0 = time.monotonic()

        client = _graph_client()
        writer = GraphWriter(client)
        n = enrich(db, evidence_id, entity_ids, writer.fetch_neighborhood)

        for fact in db.query(Fact).filter(
            Fact.evidence_id == evidence_id,
            Fact.origin == "enrichment",
            Fact.status == "pending",
        ):
            _confidence_gate(fact, db)

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
        _log(
            ev, "enrich",
            f"{n} inference proposals generated ({time.monotonic() - t0:.1f}s)",
        )
        db.add(ev)
        db.commit()
    except PipelineCancelled:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        ev = db.get(Evidence, evidence_id)
        if ev is not None:
            ev.status = "enriched"  # enrichment is best-effort; don't fail the run
            _log(ev, "enrich", f"skipped (non-fatal): {exc}")
            db.add(ev)
            db.commit()
    finally:
        db.close()
        if client is not None:
            client.close()


# --------------------------------------------------------------------------- orchestrator

def run_pipeline_inline(
    evidence_id: str,
    on_written: Callable[[tuple[int, int]], None] | None = None,
) -> None:
    init_db()
    try:
        step_parse(evidence_id)
        step_extract(evidence_id)
        step_resolve(evidence_id)
        counts = step_write(evidence_id)
        if on_written is not None:
            try:
                on_written(counts)
            except Exception:
                pass
        step_enrich(evidence_id)
    except PipelineCancelled:
        # Row already marked `cancelled` (or deleted) — stop quietly.
        return
