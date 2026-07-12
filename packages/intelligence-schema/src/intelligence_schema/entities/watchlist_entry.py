from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from intelligence_schema.entities.base import IntelligenceVertex


@dataclass
class WatchlistEntryVertex(IntelligenceVertex):
    tag: ClassVar[str] = "watchlist_entry"

    def validate(self) -> None:
        super().validate()
        if not self.properties.get("watchlist_name"):
            raise ValueError("watchlist_entry.watchlist_name is required")
