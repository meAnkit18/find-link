from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    PERSON = "Person"
    COMPANY = "Company"
    ORGANIZATION = "Organization"
    ADDRESS = "Address"
    COUNTRY = "Country"
    PASSPORT = "Passport"
    PHONE = "Phone"
    EMAIL = "Email"
    BANK_ACCOUNT = "BankAccount"
    VEHICLE = "Vehicle"


RELATIONSHIP_TYPES: dict[str, tuple[set[str], set[str]]] = {
    "WORKS_AT":     ({"Person"}, {"Company", "Organization"}),
    "OWNS":         ({"Person", "Company", "Organization"}, {"Company", "Organization", "Vehicle"}),
    "PAYS":         ({"Person", "Company", "Organization"}, {"Person", "Company", "Organization"}),
    "HAS_PASSPORT": ({"Person"}, {"Passport"}),
    "HAS_PHONE":    ({"Person", "Company", "Organization"}, {"Phone"}),
    "HAS_EMAIL":    ({"Person", "Company", "Organization"}, {"Email"}),
    "HAS_ACCOUNT":  ({"Person", "Company", "Organization"}, {"BankAccount"}),
    "OWNS_VEHICLE": ({"Person", "Company", "Organization"}, {"Vehicle"}),
    "LOCATED_AT":   ({"Person", "Company", "Organization"}, {"Address"}),
    "CITIZEN_OF":   ({"Person"}, {"Country"}),
    "RELATED_TO":   (set(EntityType._value2member_map_.keys()),
                     set(EntityType._value2member_map_.keys())),
}


class ExtractedEntity(BaseModel):
    local_id: str = Field(..., description="ID unique within this extraction")
    type: EntityType
    name: str = Field(..., min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_span: str | None = Field(None)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ExtractedRelationship(BaseModel):
    source_local_id: str
    target_local_id: str
    type: str = Field(..., description="One of RELATIONSHIP_TYPES; unknown become RELATED_TO")
    relation_label: str | None = Field(None)
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_span: str | None = None

    @field_validator("type")
    @classmethod
    def coerce_type(cls, v: str) -> str:
        v = v.strip().upper().replace(" ", "_")
        return v if v in RELATIONSHIP_TYPES else "RELATED_TO"


class ExtractionResult(BaseModel):
    evidence_id: str
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    summary: str | None = None
    overall_confidence: float = Field(0.0, ge=0.0, le=1.0)

    def validate_relationship_endpoints(self) -> ExtractionResult:
        by_id = {e.local_id: e for e in self.entities}
        kept: list[ExtractedRelationship] = []
        for rel in self.relationships:
            src, tgt = by_id.get(rel.source_local_id), by_id.get(rel.target_local_id)
            if not src or not tgt:
                continue
            allowed_src, allowed_tgt = RELATIONSHIP_TYPES[rel.type]
            if src.type.value not in allowed_src or tgt.type.value not in allowed_tgt:
                rel.relation_label = rel.relation_label or rel.type
                rel.type = "RELATED_TO"
            kept.append(rel)
        self.relationships = kept
        return self
