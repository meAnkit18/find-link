"""Field-index primitives: what gets indexed, and under which vertex id."""

from __future__ import annotations

from intelligence_schema.field_index import (
    field_values,
    is_eligible,
    normalize_value,
    value_vid,
)


def test_normalize_casefolds_and_collapses_whitespace():
    assert normalize_value("  Ahmed   Al-Mansouri ") == "ahmed al-mansouri"


def test_identifier_values_lose_their_separators():
    """784-1990-1234567-1 and 784 1990 1234567 1 are one value."""
    assert normalize_value("784-1990-1234567-1") == normalize_value("784 1990 1234567 1")
    assert normalize_value("784-1990-1234567-1") == "784199012345671"


def test_text_values_keep_their_hyphens():
    """Only values containing a digit are treated as identifiers."""
    assert normalize_value("Al-Mansouri") == "al-mansouri"


def test_blank_and_none_normalize_to_none():
    assert normalize_value(None) is None
    assert normalize_value("   ") is None


def test_denylisted_keys_are_never_eligible():
    for key in ("nationality", "Gender", "COUNTRY", "document_type", "issuing_authority"):
        assert is_eligible(key, "anything") is False


def test_short_values_and_bare_years_are_not_eligible():
    assert is_eligible("father_name", "ab") is False
    assert is_eligible("issue_year", "1990") is False
    assert is_eligible("father_name", None) is False


def test_ordinary_field_is_eligible():
    assert is_eligible("father_name", "ahmed al-mansouri") is True


def test_value_vid_is_stable_short_and_value_only():
    vid = value_vid("ahmed al-mansouri")
    assert vid == value_vid("ahmed al-mansouri")
    assert vid.startswith("value:")
    assert len(vid) <= 64
    assert vid != value_vid("ahmed al-mansour")


def test_field_values_filters_and_sorts():
    props = {
        "father_name": "Ahmed Al-Mansouri",
        "nationality": "UAE",          # denylisted
        "gender": "M",                 # denylisted
        "number": "P-123 4567",
        "issue_year": "1990",          # bare year
        "aliases": ["x", "y"],         # non-scalar
        "empty": "",
    }
    assert field_values(props) == [
        ("father_name", "ahmed al-mansouri"),
        ("number", "p1234567"),
    ]


def test_field_values_tolerates_empty_input():
    assert field_values({}) == []
    assert field_values(None) == []
