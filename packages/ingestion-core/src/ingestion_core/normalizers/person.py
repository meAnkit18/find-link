from __future__ import annotations

import re
from typing import Any


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip()


def normalize_person(raw: dict[str, Any]) -> dict[str, Any]:
    full_name = normalize_whitespace(raw.get("full_name") or raw.get("name"))
    return {
        "label": full_name,
        "entity_type": "person",
        "full_name": full_name,
        "date_of_birth": raw.get("date_of_birth"),
        "nationality": normalize_whitespace(raw.get("nationality")),
        "passport_number": normalize_whitespace(raw.get("passport_number")),
        "national_id": normalize_whitespace(raw.get("national_id")),
        "status": (raw.get("status") or "active").strip().lower(),
        "confidence": float(raw.get("confidence", 1.0)),
    }
