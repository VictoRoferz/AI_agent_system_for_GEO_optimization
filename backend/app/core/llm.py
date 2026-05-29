"""LiteLLM gateway — the single entry point for the analysis brain (role #1).

Provides one `complete_structured()` call that:
  * routes to any provider via LiteLLM (Claude default, GPT/Gemini/Qwen/Kimi switchable),
  * enables Anthropic prompt caching for the large system+KB prefix,
  * forces JSON output validated against a Pydantic schema (with one repair retry).
"""
from __future__ import annotations

import json
import os
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.core.models import ModelInfo, resolve_model

T = TypeVar("T", bound=BaseModel)

_keys_loaded = False


def _ensure_provider_keys() -> None:
    """Export configured provider keys into the environment LiteLLM reads."""
    global _keys_loaded
    if _keys_loaded:
        return
    s = get_settings()
    for env_name, value in (
        ("ANTHROPIC_API_KEY", s.anthropic_api_key),
        ("OPENAI_API_KEY", s.openai_api_key),
        ("GEMINI_API_KEY", s.gemini_api_key),
        ("OPENROUTER_API_KEY", s.openrouter_api_key),
    ):
        if value and not os.environ.get(env_name):
            os.environ[env_name] = value
    litellm.drop_params = True  # silently drop params a given provider doesn't support
    _keys_loaded = True


def _extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from a model response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences / surrounding prose by grabbing the outermost braces.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found in model response")


def _build_messages(
    system: str, user: str, model: ModelInfo, cache_prefix: str | None
) -> list[dict]:
    """Build chat messages, applying Anthropic cache_control to the stable prefix."""
    if cache_prefix and model.supports_cache_control:
        system_content = [
            # Cacheable prefix (system instructions + knowledge base): billed once,
            # reused across runs within the cache TTL.
            {"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": system},
        ]
    else:
        prefix = f"{cache_prefix}\n\n" if cache_prefix else ""
        system_content = prefix + system
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user},
    ]


async def complete_structured(
    *,
    system: str,
    user: str,
    schema: type[T],
    model_key: str | None = None,
    cache_prefix: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> T:
    """Call the selected model and return a validated instance of `schema`.

    `cache_prefix` is a large, stable block (system rubric + KB pillars) that we want
    cached on Anthropic models. It is prepended to the system message.
    """
    _ensure_provider_keys()
    model = resolve_model(model_key)

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    json_instructions = (
        "\n\nRespond with a SINGLE JSON object and nothing else. "
        "It MUST conform exactly to this JSON Schema:\n"
        f"{schema_json}"
    )
    messages = _build_messages(system + json_instructions, user, model, cache_prefix)

    last_error: Exception | None = None
    for attempt in range(2):
        response = await litellm.acompletion(
            model=model.litellm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        try:
            return schema.model_validate(_extract_json(content))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            # Repair turn: show the model its bad output and the error.
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response did not validate against the schema: {exc}. "
                        "Return ONLY a corrected JSON object."
                    ),
                }
            )
    raise RuntimeError(f"Model did not return valid structured output: {last_error}")


async def complete_text(
    *,
    system: str,
    user: str,
    model_key: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Plain free-text completion (used e.g. by Simulation to role-play an engine)."""
    _ensure_provider_keys()
    model = resolve_model(model_key)
    response = await litellm.acompletion(
        model=model.litellm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
