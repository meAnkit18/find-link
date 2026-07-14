from __future__ import annotations

import json
import os
import re

from openai import APIError, OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

_client: OpenAI | None = None

_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=os.environ.get("LLM_API_KEY", "sk-not-set"),
            timeout=_LLM_TIMEOUT,
            max_retries=0,  # tenacity handles retries; disable SDK-internal retries
        )
    return _client


def _get_model() -> str:
    return os.environ.get("LLM_MODEL", "deepseek-chat")


def _get_temperature() -> float:
    return float(os.environ.get("LLM_TEMPERATURE", "0.0"))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def chat(system: str, user: str, max_tokens: int = 4096) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=_get_model(),
        temperature=_get_temperature(),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


@retry(stop=stop_after_attempt(1), wait=wait_exponential(min=2, max=20))
def _chat_json_attempt(system: str, user: str, max_tokens: int) -> dict:
    raw = chat(
        system + "\nRespond with ONLY a valid JSON object. No markdown, no commentary.",
        user,
        max_tokens,
    )
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def chat_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    try:
        return _chat_json_attempt(system, user, max_tokens)
    except (APIError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(
            f"LLM call failed: {exc}. "
            f"Request was {len(user)} chars — the model may have returned "
            f"truncated or malformed JSON."
        ) from exc
