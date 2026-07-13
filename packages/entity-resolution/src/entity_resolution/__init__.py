from entity_resolution.models import MatchCandidate, ResolutionDecision
from entity_resolution.normalize import compute_deterministic_key
from entity_resolution.resolver import EntityResolver, ResolutionResult

__all__ = [
    "EntityResolver", "ResolutionResult",
    "MatchCandidate", "ResolutionDecision",
    "compute_deterministic_key",
]
