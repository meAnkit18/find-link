"""ingestion_core.normalize — pure functions, no pipeline/DB needed."""

from __future__ import annotations

from ingestion_core.canonical import EntityType, ExtractedEntity
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
