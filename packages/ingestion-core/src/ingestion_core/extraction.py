from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from ingestion_core.canonical import (
    RELATIONSHIP_TYPES,
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from ingestion_core.llm import chat_json

_ENTITY_TYPES = ", ".join(t.value for t in EntityType)
_REL_TYPES = ", ".join(RELATIONSHIP_TYPES.keys())
_CHUNK_CHARS = int(os.environ.get("EXTRACT_CHUNK_CHARS", "16000"))

SYSTEM_PROMPT = f"""You extract structured facts for a knowledge graph from the provided text.

Extract entities and relationships from the provided text.

ENTITY TYPES (use exactly these): {_ENTITY_TYPES}
RELATIONSHIP TYPES (use exactly these): {_REL_TYPES}

Rules:
- Give every entity a local_id like "e1", "e2", ...
- "name" is the primary surface form. Put everything else in "attributes"
  (dob, nationality, number, address components, iban, plate, role, dates...).
- Deduplicate WITHIN this text: the same real-world thing appears once.
- Relationships reference entities by local_id only.
- confidence is 0.0-1.0: how certain you are given the text.
- source_span: short verbatim snippet supporting the extraction.
- If a relationship doesn't fit a listed type, use RELATED_TO and set
  relation_label (e.g. "sibling_of", "supplier_of").
- Do NOT invent facts absent from the text.

Output JSON schema:
{{
  "entities": [{{"local_id": "e1", "type": "Person", "name": "...",
                 "attributes": {{}}, "confidence": 0.9, "source_span": "..."}}],
  "relationships": [{{"source_local_id": "e1", "target_local_id": "e2",
                      "type": "WORKS_AT", "relation_label": null,
                      "attributes": {{}}, "confidence": 0.85,
                      "source_span": "..."}}],
  "summary": "one-sentence summary of the document",
  "overall_confidence": 0.8
}}"""


def _parse_entities(raw_list: Any) -> list[ExtractedEntity]:
    if not isinstance(raw_list, list):
        return []
    entities: list[ExtractedEntity] = []
    for raw in raw_list:
        try:
            entities.append(ExtractedEntity(**raw))
        except (ValidationError, TypeError):
            continue
    return entities


def _parse_relationships(raw_list: Any) -> list[ExtractedRelationship]:
    if not isinstance(raw_list, list):
        return []
    relationships: list[ExtractedRelationship] = []
    for raw in raw_list:
        try:
            relationships.append(ExtractedRelationship(**raw))
        except (ValidationError, TypeError):
            continue
    return relationships


def _chunk_text(text: str, chunk_size: int = _CHUNK_CHARS) -> list[str]:
    """Split *text* into chunks at approximately *chunk_size* characters.

    Splits on newline boundaries when possible and adds a small overlap
    so that entities crossing a boundary are likely captured in both chunks.
    """
    if len(text) <= chunk_size:
        return [text]

    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    start = 0
    overlap = min(500, chunk_size // 8)

    while start < len(lines):
        end = start
        char_count = 0
        while end < len(lines) and char_count < chunk_size:
            char_count += len(lines[end])
            end += 1
        chunk = "".join(lines[start:end])
        chunks.append(chunk)
        # Advance to the next line boundary, but rewind a bit for overlap
        overlap_end = end
        rewind = 0
        while overlap_end > start and rewind < overlap:
            overlap_end -= 1
            rewind += len(lines[overlap_end])
        start = overlap_end

    return chunks


def _merge_results(chunks: list[ExtractionResult]) -> ExtractionResult:
    """Merge multiple chunk results into one, deduplicating by (type, name)."""
    if not chunks:
        return ExtractionResult(evidence_id="")
    merged = chunks[0]
    seen_entities = {(e.type.value, e.name) for e in merged.entities}
    for chunk in chunks[1:]:
        for e in chunk.entities:
            key = (e.type.value, e.name)
            if key not in seen_entities:
                seen_entities.add(key)
                merged.entities.append(e)
        merged.relationships.extend(chunk.relationships)
        if chunk.summary and not merged.summary:
            merged.summary = chunk.summary
        if chunk.overall_confidence > merged.overall_confidence:
            merged.overall_confidence = chunk.overall_confidence
    return merged


def extract(evidence_id: str, text: str, structured_hint: str = "") -> ExtractionResult:
    user = ""
    if structured_hint:
        user += f"SOURCE CONTEXT: {structured_hint}\n\n"

    if len(text) > _CHUNK_CHARS:
        chunks = _chunk_text(text)
        results: list[ExtractionResult] = []
        for i, chunk_text in enumerate(chunks):
            chunk_user = f"{user}PART {i + 1} OF {len(chunks)}:\n{chunk_text}"
            data = chat_json(SYSTEM_PROMPT, chunk_user, max_tokens=8192)
            raw_entities = data.get("entities", [])
            raw_relationships = data.get("relationships", [])
            raw_confidence = data.get("overall_confidence", 0.5)
            try:
                overall_confidence = float(raw_confidence)
            except (TypeError, ValueError):
                overall_confidence = 0.5
            result = ExtractionResult(
                evidence_id=evidence_id,
                entities=_parse_entities(raw_entities),
                relationships=_parse_relationships(raw_relationships),
                summary=data.get("summary"),
                overall_confidence=overall_confidence,
            )
            results.append(result.validate_relationship_endpoints())
        return _merge_results(results)

    user += f"TEXT:\n{text}"
    data = chat_json(SYSTEM_PROMPT, user, max_tokens=8192)
    raw_entities = data.get("entities", [])
    raw_relationships = data.get("relationships", [])
    raw_confidence = data.get("overall_confidence", 0.5)
    try:
        overall_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        overall_confidence = 0.5
    result = ExtractionResult(
        evidence_id=evidence_id,
        entities=_parse_entities(raw_entities),
        relationships=_parse_relationships(raw_relationships),
        summary=data.get("summary"),
        overall_confidence=overall_confidence,
    )
    return result.validate_relationship_endpoints()
