"""How much a shared value is worth as evidence of a connection.

Follows the Fellegi-Sunter shape: a field's weight is how unlikely it is to
agree by chance. A passport number two people share is near-conclusive; a
value forty people share is noise regardless of which field it sits in. The
constants below are hand-tuned starting points, deliberately gathered in one
table because they will want retuning against real data.
"""

from __future__ import annotations

from collections.abc import Iterable

# Keyed by document field key *or* by connector tag — a shared `document`
# vertex and a matching `passport_number` field are both scored from here.
WEIGHTS: dict[str, float] = {
    # Near-unique identifiers.
    "passport_number": 0.95,
    "national_id": 0.95,
    "emirates_id": 0.95,
    "number": 0.95,
    "iban": 0.95,
    "document": 0.95,
    "bank_account": 0.9,
    # Strong but not unique.
    "phone": 0.8,
    "email": 0.8,
    "vehicle": 0.8,
    "father_name": 0.7,
    "mother_name": 0.7,
    "address": 0.7,
    "dob": 0.7,
    "place_of_birth": 0.7,
    # Real leads, but plenty of people share them.
    "company": 0.4,
    "organization": 0.4,
}

# An unanticipated field still forms connections — a fixed allowlist is
# exactly what this design set out to avoid.
DEFAULT_WEIGHT = 0.5

# A value matching across *different* field keys is a weaker claim than the
# same field agreeing on both sides, but not a worthless one.
CROSS_KEY_PENALTY = 0.6

# A stored person-to-person relationship is an assertion, not an inference.
DIRECT_CONFIDENCE = 0.9

# Two people at different-but-related organisations: a real lead, a weak one.
BRIDGE_CONFIDENCE = 0.4


def weight_for(key: str) -> float:
    return WEIGHTS.get(key.strip().casefold(), DEFAULT_WEIGHT)


def rarity(owner_count: int) -> float:
    """How much a value's scarcity vouches for it.

    Two owners and nobody else scores 1.0; the value falls away as the
    crowd grows. Fewer than two owners links nobody, so it scores 0.
    """
    if owner_count < 2:
        return 0.0
    return 1.0 / (owner_count - 1)


def match_confidence(key: str, owner_count: int, same_key: bool) -> float:
    """Confidence contributed by one matching value."""
    score = weight_for(key) * rarity(owner_count) * (1.0 if same_key else CROSS_KEY_PENALTY)
    return min(1.0, max(0.0, score))


def combine(confidences: Iterable[float]) -> float:
    """Noisy-OR across independent matches.

    Two people sharing a father's name *and* an address are more connected
    than either fact alone implies, so the reasons compound rather than the
    pair being scored by its single best one.
    """
    remaining = 1.0
    for confidence in confidences:
        remaining *= 1.0 - min(1.0, max(0.0, confidence))
    return 1.0 - remaining
