from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskFactor:
    code: str
    weight: float
    value: float
    explanation: str
    evidence_ids: list[str]


@dataclass
class RiskResult:
    entity_id: str
    score: float
    level: str
    factors: list[RiskFactor]
