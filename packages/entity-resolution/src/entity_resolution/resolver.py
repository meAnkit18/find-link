from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from rapidfuzz import fuzz

from entity_resolution.models import MatchCandidate, ResolutionDecision, ResolutionResult
from entity_resolution.normalize import compute_deterministic_key

_embedder = None      # local sentence-transformers model (ER_EMBEDDING_BACKEND=local)
_hf_client = None     # Hugging Face InferenceClient (ER_EMBEDDING_BACKEND=huggingface)
_llm_client = None


def _embedding_backend() -> str:
    if os.environ.get("ER_USE_EMBEDDINGS", "true").lower() != "true":
        return "off"
    return os.environ.get("ER_EMBEDDING_BACKEND", "huggingface").lower()


def _get_embedder():
    """Local sentence-transformers model — only for ER_EMBEDDING_BACKEND=local."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        model = os.environ.get(
            "ER_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        _embedder = SentenceTransformer(model)
    except ImportError:
        pass
    return _embedder


def _get_hf_client():
    """Hugging Face Inference API client — nothing runs locally."""
    global _hf_client
    if _hf_client is not None:
        return _hf_client
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        return None
    try:
        from huggingface_hub import InferenceClient
        _hf_client = InferenceClient(provider="hf-inference", api_key=token)
    except ImportError:
        pass
    return _hf_client


def _get_llm_client():
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    try:
        from openai import OpenAI
        _llm_client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=os.environ.get("LLM_API_KEY", "sk-not-set"),
        )
    except ImportError:
        pass
    return _llm_client


@lru_cache(maxsize=4096)
def _hf_similarity(a: str, b: str) -> float:
    """Cosine similarity computed by the HF serverless Inference API.

    Cached because resolve_cascade() re-compares recurring names during an
    ingest run; each API call costs latency and free-tier credits.
    """
    client = _get_hf_client()
    if client is None:
        return 0.0
    model = os.environ.get(
        "ER_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    try:
        scores = client.sentence_similarity(a, other_sentences=[b], model=model)
        return float(scores[0])
    except Exception:
        return 0.0


def _embedding_similarity(a: str, b: str) -> float:
    backend = _embedding_backend()
    if backend == "huggingface":
        if not a or not b:
            return 0.0
        return _hf_similarity(a, b)
    if backend == "local":
        model = _get_embedder()
        if model is None:
            return 0.0
        import numpy as np
        va, vb = model.encode([a, b], normalize_embeddings=True)
        return float(np.dot(va, vb))
    return 0.0


def _llm_adjudicate(
    mention_type: str, mention_name: str, mention_attrs: dict,
    candidate_id: str, candidate_type: str, candidate_name: str,
    candidate_attrs: dict, candidate_aliases: list[str],
) -> tuple[bool, float]:
    client = _get_llm_client()
    if client is None:
        return False, 0.0
    system = (
        "You are an entity-resolution adjudicator for an intelligence "
        "knowledge graph. Decide if the NEW MENTION and the EXISTING "
        "ENTITY refer to the same real-world entity. Consider name "
        "variants, initials, nicknames, transliteration, and whether "
        "attributes (dob, nationality, employer...) agree or conflict. "
        "Conflicting hard attributes (different dob, different passport) "
        'mean DIFFERENT. Respond JSON: {"same": true/false, '
        '"confidence": 0.0-1.0, "reason": "..."}'
    )
    user = (
        f"NEW MENTION:\n type={mention_type}\n name={mention_name}\n "
        f"attributes={json.dumps(mention_attrs)}\n\n"
        f"EXISTING ENTITY:\n type={candidate_type}\n "
        f"name={candidate_name}\n aliases={json.dumps(candidate_aliases)}\n "
        f"attributes={json.dumps(candidate_attrs)}"
    )
    try:
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "deepseek-chat"),
            temperature=0.0,
            max_tokens=512,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        import json as j
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            verdict = j.loads(match.group(0))
            return bool(verdict.get("same")), float(verdict.get("confidence", 0.5))
    except Exception:
        pass
    return False, 0.0


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
            return ResolutionDecision(
                action="merge", entity_id=best.entity_id, candidates=candidates,
            )
        if best.score >= 0.70:
            return ResolutionDecision(action="review", entity_id=None, candidates=candidates)
        return ResolutionDecision(action="create", entity_id=None, candidates=[])

    def resolve_cascade(
        self, entity_type: str, payload: dict,
    ) -> ResolutionResult:
        det_key = compute_deterministic_key(entity_type, payload)
        if det_key:
            entity_id = self.search_gateway.find_by_deterministic_key(det_key)
            if entity_id:
                self._merge_in_graph(entity_type, entity_id, payload, det_key=det_key)
                return ResolutionResult(
                    entity_id=entity_id, is_new=False, method="deterministic", score=1.0,
                )

        candidates = self._find_candidates(entity_type, payload)
        if candidates:
            best_score, best_cand = candidates[0].score, candidates[0]
            if best_score >= float(os.environ.get("ER_FUZZY_AUTO", "0.93")):
                self._merge_in_graph(entity_type, best_cand.entity_id, payload)
                return ResolutionResult(
                    entity_id=best_cand.entity_id, is_new=False, method="fuzzy", score=best_score,
                )

            for cand in candidates[:3]:
                score = best_score
                emb = _embedding_similarity(
                    payload.get("label", ""),
                    cand.entity_id,
                )
                score = max(score, emb)
                if score >= float(os.environ.get("ER_FUZZY_CANDIDATE", "0.75")):
                    cand_payload = self.search_gateway.get_entity_payload(cand.entity_id)
                    same, llm_conf = _llm_adjudicate(
                        mention_type=entity_type,
                        mention_name=payload.get("label", ""),
                        mention_attrs=payload,
                        candidate_id=cand.entity_id,
                        candidate_type=entity_type,
                        candidate_name=cand_payload.get("label", ""),
                        candidate_attrs=cand_payload,
                        candidate_aliases=cand_payload.get("aliases", []),
                    )
                    if same and llm_conf >= 0.7:
                        self._merge_in_graph(entity_type, cand.entity_id, payload)
                        return ResolutionResult(
                            entity_id=cand.entity_id, is_new=False,
                            method="embedding+llm", score=max(score, llm_conf),
                        )

        entity_id = self._create_in_graph(entity_type, payload, det_key=det_key)
        return ResolutionResult(entity_id=entity_id, is_new=True, method="new", score=1.0)

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
            score = fuzz.token_sort_ratio(label.lower(), (row.get("label") or "").lower()) / 100.0
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

    def _merge_in_graph(
        self, entity_type: str, entity_id: str, payload: dict,
        det_key: str | None = None,
    ) -> None:
        self.search_gateway.merge_entity(entity_type, entity_id, payload)

    def _create_in_graph(
        self, entity_type: str, payload: dict,
        det_key: str | None = None,
    ) -> str:
        return self.search_gateway.create_entity(entity_type, payload)
