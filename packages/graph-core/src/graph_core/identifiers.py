"""Shared identifier validation.

NebulaGraph's nGQL has no parameterization for identifiers (tag names, edge
type names, property names) — they must be validated against an allowlist,
not escaped. This is the single copy of that check; every layer that needs
it (config space name, query builder tag/edge/property names, metadata
tag/edge/index names) imports this rather than re-implementing the regex.
"""

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str, kind: str) -> None:
    """Raise ValueError if `name` is not a safe NebulaGraph identifier."""
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid {kind} identifier: {name!r}")
