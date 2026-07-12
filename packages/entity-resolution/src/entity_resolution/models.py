from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MatchCandidate:
    entity_id: str
    score: float
    reasons: list[str]


@dataclass
class ResolutionDecision:
    action: str  # create | merge | review
    entity_id: str | None
    candidates: list[MatchCandidate]
