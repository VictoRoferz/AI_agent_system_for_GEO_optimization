"""Registry of selectable analysis-brain models (role #1).

Each entry maps a stable UI key -> a LiteLLM model string + display metadata.
LiteLLM routes the call to the right provider based on the model string prefix.
Adjust the `litellm_model` strings to whatever model ids your accounts have access to;
the UI and the rest of the app only ever reference the stable `key`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    key: str
    label: str
    litellm_model: str
    provider: str
    supports_cache_control: bool = False  # Anthropic prompt caching via cache_control blocks


MODEL_REGISTRY: dict[str, ModelInfo] = {
    "claude-default": ModelInfo(
        key="claude-default",
        label="Claude Sonnet (default)",
        litellm_model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        supports_cache_control=True,
    ),
    "claude-opus": ModelInfo(
        key="claude-opus",
        label="Claude Opus",
        litellm_model="anthropic/claude-opus-4-8",
        provider="anthropic",
        supports_cache_control=True,
    ),
    "gpt": ModelInfo(
        key="gpt",
        label="OpenAI GPT",
        litellm_model="openai/gpt-4o",
        provider="openai",
    ),
    "gemini": ModelInfo(
        key="gemini",
        label="Google Gemini",
        litellm_model="gemini/gemini-2.5-pro",
        provider="gemini",
    ),
    "qwen": ModelInfo(
        key="qwen",
        label="Qwen (via OpenRouter)",
        litellm_model="openrouter/qwen/qwen-2.5-72b-instruct",
        provider="openrouter",
    ),
    "kimi": ModelInfo(
        key="kimi",
        label="Kimi (via OpenRouter)",
        litellm_model="openrouter/moonshotai/kimi-k2",
        provider="openrouter",
    ),
}


def resolve_model(key: str | None) -> ModelInfo:
    """Resolve a UI model key to its ModelInfo, falling back to the default."""
    if key and key in MODEL_REGISTRY:
        return MODEL_REGISTRY[key]
    return MODEL_REGISTRY["claude-default"]
