"""Scoring an inferred connection.

A field's worth is how unlikely it is to agree by chance — a near-unique
identifier is strong evidence, a value forty people share is not.
"""

from __future__ import annotations

import pytest

from graph_explorer_api.services.connection_confidence import (
    CROSS_KEY_PENALTY,
    DEFAULT_WEIGHT,
    combine,
    match_confidence,
    rarity,
    weight_for,
)


def test_identifier_fields_outweigh_soft_fields():
    assert weight_for("passport_number") > weight_for("father_name")
    assert weight_for("father_name") > weight_for("company")


def test_weight_lookup_is_case_insensitive():
    assert weight_for("Father_Name") == weight_for("father_name")


def test_unknown_keys_get_the_default_weight():
    """An unanticipated field still forms connections — that's the point."""
    assert weight_for("grandfather_maiden_name") == DEFAULT_WEIGHT


def test_rarity_falls_as_more_people_share_a_value():
    assert rarity(2) == 1.0
    assert rarity(3) == 0.5
    assert rarity(11) == pytest.approx(0.1)


def test_rarity_of_an_unshared_value_is_zero():
    """One owner links nobody."""
    assert rarity(1) == 0.0
    assert rarity(0) == 0.0


def test_cross_key_matches_are_penalised():
    same = match_confidence("father_name", 2, same_key=True)
    cross = match_confidence("father_name", 2, same_key=False)
    assert cross == pytest.approx(same * CROSS_KEY_PENALTY)
    assert cross < same


def test_common_value_scores_near_zero_even_for_a_strong_field():
    assert match_confidence("passport_number", 200, same_key=True) < 0.01


def test_confidence_stays_within_bounds():
    for count in (1, 2, 3, 50):
        for same in (True, False):
            assert 0.0 <= match_confidence("passport_number", count, same) <= 1.0


def test_combine_compounds_independent_matches():
    """Two medium signals beat either alone — noisy-OR, not max."""
    combined = combine([0.5, 0.5])
    assert combined == pytest.approx(0.75)
    assert combined > 0.5


def test_combine_of_one_is_itself():
    assert combine([0.42]) == pytest.approx(0.42)


def test_combine_of_nothing_is_zero():
    assert combine([]) == 0.0


def test_combine_never_exceeds_one():
    assert combine([0.9, 0.9, 0.9, 0.9]) <= 1.0
