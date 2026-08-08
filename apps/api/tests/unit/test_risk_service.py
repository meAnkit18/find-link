"""PEP classification — free text from whatever screening source wrote it."""

from __future__ import annotations

import pytest

from graph_explorer_api.services.risk_service import classify_pep
from risk_engine.scorer import PEP_ASSOCIATE, PEP_SELF


@pytest.mark.parametrize("status", [
    None, "", "  ", "No", "no", "NONE", "false", "Not a PEP", "n/a", "-",
])
def test_plainly_negative_values_are_not_a_pep(status):
    assert classify_pep(status) is None


@pytest.mark.parametrize("status", [
    "Yes", "Yes — domestic, senior government (former)",
    "PEP", "Head of state", "yes, foreign PEP",
])
def test_a_positive_status_is_the_pep_themselves(status):
    assert classify_pep(status) == PEP_SELF


@pytest.mark.parametrize("status", [
    "Yes — immediate family of a PEP",
    "Yes — known close associate of a PEP",
    "Relative of a PEP",
    "Spouse of a foreign official",
    "RCA",
])
def test_family_and_associates_are_distinguished_from_the_pep(status):
    assert classify_pep(status) == PEP_ASSOCIATE


def test_unrecognised_text_errs_towards_flagging():
    """An unparseable status is a reason to look, not a reason to skip."""
    assert classify_pep("under assessment") == PEP_SELF
