"""Which field values are worth indexing, and under what vertex id.

Two people are connected when their documents agree on a value. To find that
without scanning every document, each eligible value becomes a `field_value`
vertex that both people attach to — so "agreeing on a value" is stored as
"attached to the same vertex", which the person projection already knows how
to walk.

The vertex is keyed by the *normalised value alone*, never by (key, value).
That is deliberate: it lets a value stored under `father_name` on one
document match the same value stored under `guarantor_name` on another. Which
key each side used lives on the edge, so the projection can still tell a
same-key match from a cross-key one and score them differently.
"""

from __future__ import annotations

import hashlib
import re

# Fields that agree constantly by coincidence. Indexing them would connect
# every UAE national to every other one and drown the real leads.
DENYLISTED_KEYS = frozenset({
    "nationality",
    "gender",
    "sex",
    "country",
    "document_type",
    "issuer",
    "issuing_authority",
    "issuing_country",
})

MIN_VALUE_LENGTH = 3

_WHITESPACE = re.compile(r"\s+")
_SEPARATORS = re.compile(r"[\s\-/.]")
_BARE_YEAR = re.compile(r"^\d{4}$")


def normalize_value(raw: object) -> str | None:
    """The form a value is indexed under, or None if it is not indexable.

    Values containing a digit are treated as identifiers and lose their
    separators, so `784-1990-1234567-1` and `784 1990 1234567 1` land on one
    vertex. Text keeps its punctuation — stripping hyphens from names would
    be harmless but pointless, and keeping them makes the stored value
    readable in a link explanation.
    """
    if raw is None:
        return None
    text = _WHITESPACE.sub(" ", str(raw)).strip().casefold()
    if not text:
        return None
    if any(ch.isdigit() for ch in text):
        text = _SEPARATORS.sub("", text)
    return text or None


def is_eligible(field_key: str, normalized: str | None) -> bool:
    """Whether this (key, normalised value) should enter the index."""
    if field_key.strip().casefold() in DENYLISTED_KEYS:
        return False
    if not normalized or len(normalized) < MIN_VALUE_LENGTH:
        return False
    if _BARE_YEAR.match(normalized):
        return False
    return True


def value_vid(normalized: str) -> str:
    """Vertex id for a normalised value. Hashed because the value itself can
    exceed the space's FIXED_STRING(64) vid width."""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:32]
    return f"value:{digest}"


def field_values(props: dict | None) -> list[tuple[str, str]]:
    """Every indexable (field_key, normalised value) in a property bag.

    Non-scalar values (lists such as `aliases`, nested dicts) are skipped —
    they have no single value to match on.
    """
    found: set[tuple[str, str]] = set()
    for key, raw in (props or {}).items():
        if isinstance(raw, (dict, list, tuple, set)):
            continue
        normalized = normalize_value(raw)
        if is_eligible(str(key), normalized):
            found.add((str(key), normalized))
    return sorted(found)
