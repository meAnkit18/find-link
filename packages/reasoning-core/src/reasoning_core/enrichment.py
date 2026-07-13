from __future__ import annotations

import json
import os
import re

from sqlalchemy.orm import Session

from evidence_core.db_models import EntityRegistry, Fact


def _llm_chat_json(system: str, user: str) -> dict:
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=os.environ.get("LLM_API_KEY", "sk-not-set"),
        )
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "deepseek-chat"),
            temperature=0.0,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw)
    except Exception:
        return {"proposals": []}


_REL_TYPES = [
    "RELATED_TO", "WORKS_AT", "OWNS", "PAYS", "HAS_PASSPORT",
    "HAS_PHONE", "HAS_EMAIL", "HAS_ACCOUNT", "OWNS_VEHICLE",
    "LOCATED_AT", "CITIZEN_OF",
]

_INFER_SYSTEM = (
    "You are a graph-enrichment analyst. Given a set of KNOWN "
    "facts from a knowledge graph, propose additional "
    "relationships that logically follow but are not yet present. "
    "Only propose links justified by the given facts (e.g. "
    "A owns company X and company X pays company Y implies a "
    "financial link between A and Y). Allowed relationship types: "
    + ", ".join(_REL_TYPES) +
    '. Respond JSON: {"proposals": [{"source_id": "...", '
    '"target_id": "...", "type": "...", "relation_label": "...", '
    '"confidence": 0.0-1.0, "reason": "..."}]}. Return an empty '
    "list when nothing new follows. Never restate existing edges."
)


def enrich(
    db: Session,
    evidence_id: str,
    entity_ids: list[str],
    neighborhood_fetcher,
) -> int:
    proposals = _rule_shared_identifier(db, entity_ids, neighborhood_fetcher)
    proposals += _llm_infer(entity_ids, neighborhood_fetcher)

    created = 0
    for p in proposals:
        if p["source_id"] == p["target_id"]:
            continue
        if _duplicate_exists(db, p["source_id"], p["target_id"], p["type"]):
            continue
        fact = Fact(
            evidence_id=evidence_id,
            kind="relationship",
            origin="enrichment",
            payload={
                "type": p["type"],
                "relation_label": p.get("relation_label"),
                "attributes": {"reason": p.get("reason", "")},
            },
            resolved_source_id=p["source_id"],
            resolved_target_id=p["target_id"],
            confidence=float(p.get("confidence", 0.5)),
            status="pending",
        )
        db.add(fact)
        created += 1
    db.commit()
    return created


def _duplicate_exists(db: Session, src: str, dst: str, rel_type: str) -> bool:
    existing = (
        db.query(Fact)
        .filter(
            Fact.kind == "relationship",
            Fact.origin == "enrichment",
            Fact.resolved_source_id == src,
            Fact.resolved_target_id == dst,
        )
        .all()
    )
    for f in existing:
        if f.payload.get("type") == rel_type:
            return True
    return False


def _rule_shared_identifier(
    db: Session, entity_ids: list[str],
    neighborhood_fetcher,
) -> list[dict]:
    proposals = []
    regs = db.query(EntityRegistry).filter(EntityRegistry.id.in_(entity_ids)).all()
    for reg in regs:
        if reg.type not in ("Phone", "Email", "Address", "BankAccount"):
            continue
        neigh = neighborhood_fetcher(reg.id, depth=1, limit=100)
        holders = sorted({
            r["src"] for r in neigh
            if r["rel"] in ("HAS_PHONE", "HAS_EMAIL", "LOCATED_AT", "HAS_ACCOUNT")
        })
        for i in range(len(holders)):
            for j in range(i + 1, len(holders)):
                proposals.append({
                    "type": "RELATED_TO",
                    "relation_label": f"shares_{reg.type.lower()}",
                    "source_id": holders[i],
                    "target_id": holders[j],
                    "confidence": 0.65,
                    "reason": f"Both linked to {reg.type} '{reg.canonical_name}'",
                })
    return proposals


def _llm_infer(
    entity_ids: list[str],
    neighborhood_fetcher,
) -> list[dict]:
    id_set: set[str] = set(entity_ids)
    edges: list[dict] = []
    for eid in entity_ids:
        for row in neighborhood_fetcher(eid, depth=2, limit=40):
            id_set.update((row["src"], row["dst"]))
            edges.append(row)

    if not edges:
        return []

    names = {}
    fact_lines = set()
    for e in edges:
        src_label = names.get(e["src"], e["src"])
        dst_label = names.get(e["dst"], e["dst"])
        fact_lines.add(
            f'{src_label} --{e["rel"]}--> {dst_label} [{e["status"]}]'
        )

    id_lines = [f"{rid} = {names.get(rid, rid)}" for rid in id_set]
    user = (
        "ENTITY IDS:\n" + "\n".join(id_lines) +
        "\n\nKNOWN FACTS:\n" + "\n".join(sorted(fact_lines)) +
        "\n\nUse the raw IDs (left side of ENTITY IDS) in your proposals."
    )
    data = _llm_chat_json(_INFER_SYSTEM, user)
    valid_ids = {e["src"] for e in edges} | {e["dst"] for e in edges}
    out = []
    for p in data.get("proposals", []):
        if (
            p.get("source_id") in valid_ids
            and p.get("target_id") in valid_ids
            and p.get("type") in _REL_TYPES
        ):
            out.append(p)
    return out
