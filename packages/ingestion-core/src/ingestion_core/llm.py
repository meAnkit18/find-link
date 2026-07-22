from __future__ import annotations

import json
import os
import re

from openai import APIError, OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_client: OpenAI | None = None

_LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))


class LLMTruncatedOutput(Exception):
    """The model hit max_tokens and returned an incomplete answer.

    Retrying the identical request is pointless (temperature is 0);
    the caller must send less input instead (see extraction._extract_part).
    """


class LLMOutputError(RuntimeError):
    """LLM returned unusable output after retries. `truncated` tells the
    caller whether shrinking the input is likely to help."""

    def __init__(self, message: str, truncated: bool = False) -> None:
        super().__init__(message)
        self.truncated = truncated


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


def _json_mode_enabled() -> bool:
    # Most OpenAI-compatible endpoints (OpenAI, DeepSeek, ...) support
    # response_format={"type": "json_object"}. If yours rejects it,
    # set LLM_JSON_MODE=false in .env.
    return os.environ.get("LLM_JSON_MODE", "true").lower() == "true"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=20),
    retry=retry_if_not_exception_type(LLMTruncatedOutput),
    reraise=True,
)
def chat(system: str, user: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
    client = _get_client()
    kwargs: dict = {}
    if json_mode and _json_mode_enabled():
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=_get_model(),
        temperature=_get_temperature(),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    choice = resp.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise LLMTruncatedOutput(
            f"output hit the max_tokens={max_tokens} ceiling "
            f"(input was {len(user)} chars) — send less input per call"
        )
    return choice.message.content or ""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=20),
    retry=retry_if_exception_type(json.JSONDecodeError),
    reraise=True,
)
def _chat_json_attempt(system: str, user: str, max_tokens: int) -> dict:
    raw = chat(
        system + "\nRespond with ONLY a valid JSON object. No markdown, no commentary.",
        user,
        max_tokens,
        json_mode=True,
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
    except LLMTruncatedOutput as exc:
        raise LLMOutputError(
            f"LLM output was truncated: {exc}", truncated=True
        ) from exc
    except (APIError, json.JSONDecodeError, KeyError) as exc:
        raise LLMOutputError(
            f"LLM call failed: {exc}. "
            f"Request was {len(user)} chars — the model may have returned "
            f"truncated or malformed JSON."
        ) from exc
