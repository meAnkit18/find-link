from ingestion_core.canonical import (
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from ingestion_core.normalize import (
    deterministic_key,
    normalize_email,
    normalize_extraction,
    normalize_phone,
)
from ingestion_core.parsers import detect_source_type, get_parser

__all__ = [
    "ExtractionResult", "ExtractedEntity", "ExtractedRelationship", "EntityType",
    "normalize_extraction", "deterministic_key", "normalize_phone", "normalize_email",
    "detect_source_type", "get_parser",
]
