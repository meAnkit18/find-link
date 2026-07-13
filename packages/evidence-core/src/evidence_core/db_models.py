from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Index, Integer, String, Text

from evidence_core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_name = Column(String(512), nullable=False)
    source_type = Column(String(32), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    stored_path = Column(String(1024), nullable=True)
    raw_text = Column(Text, nullable=True)
    uploaded_by = Column(String(128), default="anonymous")
    uploaded_at = Column(DateTime(timezone=True), default=utcnow)
    status = Column(String(32), default="uploaded")
    cancel_requested = Column(Boolean, default=False, nullable=False)
    error = Column(Text, nullable=True)
    extraction_json = Column(JSON, nullable=True)
    processing_log = Column(JSON, default=list)


class EntityRegistry(Base):
    __tablename__ = "entity_registry"

    id = Column(String(36), primary_key=True, default=_uuid)
    type = Column(String(32), nullable=False, index=True)
    canonical_name = Column(String(512), nullable=False)
    deterministic_key = Column(String(256), nullable=True, unique=True, index=True)
    aliases = Column(JSON, default=list)
    attributes = Column(JSON, default=dict)
    confidence = Column(Float, default=0.0)
    evidence_ids = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_registry_type_name", "type", "canonical_name"),)


class Fact(Base):
    __tablename__ = "facts"

    id = Column(String(36), primary_key=True, default=_uuid)
    evidence_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    payload = Column(JSON, nullable=False)
    resolved_entity_id = Column(String(36), nullable=True)
    resolved_source_id = Column(String(36), nullable=True)
    resolved_target_id = Column(String(36), nullable=True)
    confidence = Column(Float, default=0.0)
    status = Column(String(16), default="pending", index=True)
    origin = Column(String(16), default="extraction")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_id = Column(String(36), nullable=False, index=True)
    evidence_id = Column(String(36), nullable=False)
    reason = Column(String(256), nullable=False)
    detail = Column(JSON, default=dict)
    state = Column(String(16), default="open", index=True)
    decided_by = Column(String(128), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
