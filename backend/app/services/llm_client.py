"""LLM backend for the agent pipeline, with two interchangeable providers.

`LLM_PROVIDER=anthropic` uses the Claude API. `LLM_PROVIDER=ollama` uses a
local model over Ollama's HTTP API - free, offline, and therefore immune to the
venue-wifi failure spec Section 13 warns about.

Both paths return a validated Pydantic object, so the agents never parse free
text and never branch on which provider is in use.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings

# Latest and most capable Claude model. Effort is tuned per call rather than
# dropping to a smaller model - a wrong number costs more than a few cents.
MODEL = "claude-opus-5"

# Extraction is narrow; the reasoning-heavy work is verification.
EFFORT_EXTRACTION = "low"
EFFORT_REASONING = "medium"

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """The provider is unreachable, unconfigured, or declined to answer."""


def provider() -> str:
    return get_settings().llm_provider.strip().lower()


@lru_cache
def _anthropic_client():
    import anthropic

    key = get_settings().anthropic_api_key
    if not key or not key.startswith("sk-"):
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not set in backend/.env. Set it, or switch to "
            "the local model with LLM_PROVIDER=ollama."
        )
    return anthropic.Anthropic(api_key=key)


# Fields the grounding checks read but the model must not see. Shown the
# projection's `projected_year`, a 7B model cited it as though the field name
# were a source: "around 2044 (projected_year: 2044, citation:
# projection.confidence_note)". The year is already in confidence_note as
# prose, which is where an answer should get it from.
INTERNAL_KEYS = frozenset({"projected_year", "from_year"})


def slim_for_prompt(data: dict) -> dict:
    """Drop bulk the model never cites individually, to cut token spend.

    `stations_used` can hold 70+ names; an answer only ever refers to how many
    there were, which confidence_note already states.
    """
    out = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # stations_used is a list of names from the depletion tool but a
            # plain count in the calculation agent's projection - only collapse
            # the list form.
            value = {
                k: (
                    f"[{len(v)} stations]"
                    if k == "stations_used" and isinstance(v, list)
                    else v
                )
                for k, v in value.items()
                if k not in INTERNAL_KEYS
            }
        elif isinstance(value, list) and len(value) > 25:
            value = value[:25] + [f"...and {len(value) - 25} more"]
        out[key] = value
    return out


def parse_structured(
    system: str,
    user: str,
    schema: type[T],
    effort: str = EFFORT_REASONING,
    max_tokens: int = 2048,
) -> T:
    """Get a schema-valid object back from whichever provider is configured."""
    if provider() == "ollama":
        return _ollama_structured(system, user, schema, max_tokens)
    return _anthropic_structured(system, user, schema, effort, max_tokens)


def _anthropic_structured(
    system: str, user: str, schema: type[T], effort: str, max_tokens: int
) -> T:
    client = _anthropic_client()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        output_format=schema,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user}],
    )
    # Classifiers can decline a request: a normal 200 with empty content, so
    # reading parsed_output blindly would fail confusingly.
    if response.stop_reason == "refusal":
        raise LLMUnavailable("The model declined to answer this request.")
    return response.parsed_output


def _ollama_structured(
    system: str, user: str, schema: type[T], max_tokens: int
) -> T:
    settings = get_settings()
    try:
        reply = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Ollama constrains decoding to this JSON Schema, the local
                # equivalent of the Claude API's structured outputs.
                "format": schema.model_json_schema(),
                "stream": False,
                "options": {"temperature": 0, "num_predict": max_tokens},
            },
            timeout=180.0,
        )
        reply.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMUnavailable(
            f"Could not reach Ollama at {settings.ollama_base_url} ({exc}). "
            f"Is `ollama serve` running?"
        ) from exc

    content = reply.json().get("message", {}).get("content", "")
    try:
        return schema.model_validate_json(content)
    except ValidationError:
        # A small model can run out of output tokens partway through the JSON,
        # especially on long retrieved passages. One retry with more room.
        if max_tokens < 4096:
            return _ollama_structured(system, user, schema, 4096)
        raise LLMUnavailable(
            f"{settings.ollama_model} could not produce a valid response for "
            f"this question, even with a longer output budget."
        ) from None


def generate_text(
    system: str, user: str, effort: str = EFFORT_REASONING, max_tokens: int = 2048
) -> str:
    """Plain text generation, for callers that do not need a schema."""
    if provider() == "ollama":
        settings = get_settings()
        try:
            reply = httpx.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": max_tokens},
                },
                timeout=180.0,
            )
            reply.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach Ollama ({exc}).") from exc
        return reply.json().get("message", {}).get("content", "").strip()

    client = _anthropic_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        raise LLMUnavailable("The model declined to answer this request.")
    return "".join(b.text for b in response.content if b.type == "text").strip()


def describe() -> str:
    """Human-readable description of the active backend, for /health."""
    settings = get_settings()
    if provider() == "ollama":
        return f"ollama:{settings.ollama_model}"
    return f"anthropic:{MODEL}"


def reachable() -> bool:
    """Cheap liveness check that does not spend tokens."""
    settings = get_settings()
    if provider() == "ollama":
        try:
            r = httpx.get(f"{settings.ollama_base_url}/api/version", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False
    key = settings.anthropic_api_key
    return bool(key) and key.startswith("sk-")


__all__ = [
    "EFFORT_EXTRACTION",
    "EFFORT_REASONING",
    "MODEL",
    "LLMUnavailable",
    "describe",
    "generate_text",
    "parse_structured",
    "provider",
    "reachable",
    "slim_for_prompt",
]
