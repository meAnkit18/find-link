"""ingestion_core.normalize — pure functions, no pipeline/DB needed."""

from __future__ import annotations

from ingestion_core.canonical import RELATIONSHIP_TYPES, EntityType, ExtractedEntity
from ingestion_core.normalize import deterministic_key, normalize_national_id


def _person(**attrs) -> ExtractedEntity:
    return ExtractedEntity(
        local_id="e1", type=EntityType.PERSON, name="Nishin Saleem",
        attributes=attrs, confidence=0.9,
    )


def test_normalize_national_id_strips_separators_and_uppercases():
    assert normalize_national_id("784-1988-9764606-7") == "784198897646067"
    assert normalize_national_id(" ab 12 ") == "AB12"


def test_deterministic_key_matches_same_id_regardless_of_formatting():
    a = deterministic_key(_person(national_id="784-1988-9764606-7"))
    b = deterministic_key(_person(national_id="7841988 9764606 7"))
    assert a == b == "national_id:784198897646067"


def test_deterministic_key_none_without_national_id():
    assert deterministic_key(_person(nationality="India")) is None


# ----------------------------------------------------------------- documents


def _doc(number: str, document_type: str) -> ExtractedEntity:
    return ExtractedEntity(
        local_id="e1",
        type=EntityType.DOCUMENT,
        name=number,
        attributes={"number": number, "document_type": document_type},
        confidence=0.9,
    )


def test_document_is_an_entity_type():
    assert EntityType.DOCUMENT.value == "Document"
    assert not hasattr(EntityType, "PASSPORT")


def test_has_document_replaces_has_passport():
    assert "HAS_PASSPORT" not in RELATIONSHIP_TYPES
    assert RELATIONSHIP_TYPES["HAS_DOCUMENT"] == ({"Person"}, {"Document"})


def test_deterministic_key_separates_document_types():
    """An Emirates ID and a passport that happen to share a number are two
    different documents, so the key includes the type."""
    assert (
        deterministic_key(_doc("784-1990-1234567-1", "emirates_id"))
        == "document:EMIRATES_ID:784199012345671"
    )
    assert deterministic_key(_doc("P1234567", "passport")) == "document:PASSPORT:P1234567"
    assert deterministic_key(_doc("X1", "passport")) != deterministic_key(_doc("X1", "emirates_id"))


def test_deterministic_key_ignores_document_number_separators():
    with_seps = deterministic_key(_doc("P-123 4567", "passport"))
    without = deterministic_key(_doc("P1234567", "passport"))
    assert with_seps == without


def test_document_without_type_defaults_to_document():
    entity = ExtractedEntity(
        local_id="e1", type=EntityType.DOCUMENT, name="P1234567",
        attributes={"number": "P1234567"}, confidence=0.9,
    )
    assert deterministic_key(entity) == "document:DOCUMENT:P1234567"
