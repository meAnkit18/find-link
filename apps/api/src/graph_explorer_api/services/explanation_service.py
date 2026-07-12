from __future__ import annotations

from reasoning_core.service import ExplanationService as CoreExplanationService
from risk_engine.models import RiskResult


class InvestigationExplanationService:
    def __init__(self) -> None:
        self._core = CoreExplanationService()

    def explain_risk(self, risk: RiskResult) -> dict:
        return self._core.explain_risk_result(risk)
