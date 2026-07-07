"""Turn arbitrary user-facing text (filenames, CSV headers) into valid
NebulaGraph identifiers (tag/edge-type/property names): ^[A-Za-z_][A-Za-z0-9_]*$
"""

from __future__ import annotations

import re

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_]+")


def sanitize_identifier(text: str, fallback: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", text.strip()).strip("_").lower()
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned
