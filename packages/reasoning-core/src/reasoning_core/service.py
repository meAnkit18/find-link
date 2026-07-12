from __future__ import annotations

from risk_engine.models import RiskResult


class ExplanationService:
    def explain_risk_result(self, risk: RiskResult) -> dict:
        if not risk.factors:
            summary = (
                "No significant risk indicators were detected "
                "based on the current graph evidence."
            )
        else:
            reason_lines = [factor.explanation for factor in risk.factors]
            summary = " ".join(reason_lines)

        return {
            "entity_id": risk.entity_id,
            "score": risk.score,
            "level": risk.level,
            "summary": summary,
            "factors": [
                {
                    "code": factor.code,
                    "explanation": factor.explanation,
                    "evidence_ids": factor.evidence_ids,
                }
                for factor in risk.factors
            ],
        }
