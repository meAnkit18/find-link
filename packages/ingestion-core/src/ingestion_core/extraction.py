from __future__ import annotations

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


def extract(evidence_id: str, text: str, structured_hint: str = "") -> ExtractionResult:
    user = ""
    if structured_hint:
        user += f"SOURCE CONTEXT: {structured_hint}\n\n"
    user += f"TEXT:\n{text}"

    data = chat_json(SYSTEM_PROMPT, user, max_tokens=8192)

    entities: list[ExtractedEntity] = []
    for raw in data.get("entities", []):
        try:
            entities.append(ExtractedEntity(**raw))
        except ValidationError:
            continue

    relationships: list[ExtractedRelationship] = []
    for raw in data.get("relationships", []):
        try:
            relationships.append(ExtractedRelationship(**raw))
        except ValidationError:
            continue

    result = ExtractionResult(
        evidence_id=evidence_id,
        entities=entities,
        relationships=relationships,
        summary=data.get("summary"),
        overall_confidence=float(data.get("overall_confidence", 0.5)),
    )
    return result.validate_relationship_endpoints()
