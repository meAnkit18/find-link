from __future__ import annotations

from difflib import SequenceMatcher

from entity_resolution.models import MatchCandidate, ResolutionDecision


class EntityResolver:
    def __init__(self, search_gateway) -> None:
        self.search_gateway = search_gateway

    def resolve(self, entity_type: str, payload: dict) -> ResolutionDecision:
        exact = self._try_exact_match(entity_type, payload)
        if exact is not None:
            return ResolutionDecision(action="merge", entity_id=exact.entity_id, candidates=[exact])

        candidates = self._find_candidates(entity_type, payload)
        if not candidates:
            return ResolutionDecision(action="create", entity_id=None, candidates=[])

        best = candidates[0]
        if best.score >= 0.92:
            return ResolutionDecision(action="merge", entity_id=best.entity_id, candidates=candidates)
        if best.score >= 0.70:
            return ResolutionDecision(action="review", entity_id=None, candidates=candidates)
        return ResolutionDecision(action="create", entity_id=None, candidates=[])

    def _try_exact_match(self, entity_type: str, payload: dict) -> MatchCandidate | None:
        passport_number = payload.get("passport_number")
        national_id = payload.get("national_id")
        if passport_number:
            entity_id = self.search_gateway.find_by_unique_field(
                entity_type, "passport_number", passport_number
            )
            if entity_id:
                return MatchCandidate(
                    entity_id=entity_id, score=1.0, reasons=["passport_number exact match"]
                )
        if national_id:
            entity_id = self.search_gateway.find_by_unique_field(
                entity_type, "national_id", national_id
            )
            if entity_id:
                return MatchCandidate(
                    entity_id=entity_id, score=1.0, reasons=["national_id exact match"]
                )
        return None

    def _find_candidates(self, entity_type: str, payload: dict) -> list[MatchCandidate]:
        label = payload.get("label") or ""
        existing = self.search_gateway.search_similar(entity_type, label)
        scored: list[MatchCandidate] = []

        for row in existing:
            score = SequenceMatcher(None, label.lower(), row["label"].lower()).ratio()
            reasons = [f"name similarity={score:.2f}"]
            if (
                payload.get("date_of_birth")
                and row.get("date_of_birth") == payload.get("date_of_birth")
            ):
                score += 0.10
                reasons.append("date_of_birth match")
            if payload.get("nationality") and row.get("nationality") == payload.get("nationality"):
                score += 0.05
                reasons.append("nationality match")
            scored.append(
                MatchCandidate(entity_id=row["entity_id"], score=min(score, 1.0), reasons=reasons)
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:5]
