from __future__ import annotations

from runtime.ai.config import AIConfig, load_ai_config
from runtime.ai.http_openai_compatible_provider import OpenAICompatibleHttpProvider
from runtime.ai.mock_provider import MockAIProvider
from runtime.ai.provider import AIProvider

# Providers that represent a REAL LLM call (as opposed to "mock", which
# returns canned/no-op responses). AI-based legal review must only be
# considered "active" when one of these is configured with an api_key.
REAL_AI_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic"})


def is_ai_enabled(config: AIConfig | None = None) -> bool:
    """Return True iff a real (non-mock) AI provider with an API key is configured.

    This is the single source of truth for "should AI-based legal review run,
    or should the pipeline fall back to the rule engine" — every call site
    that previously hardcoded `cfg.provider == "openai" and cfg.api_key`
    (which silently ignored a configured Anthropic key) must go through this
    function instead.
    """
    cfg = config or load_ai_config()
    provider = (cfg.provider or "").strip().lower()
    return provider in REAL_AI_PROVIDERS and bool(cfg.api_key)


def create_ai_provider(config: AIConfig | None = None) -> AIProvider:
    cfg = config or load_ai_config()
    provider = (cfg.provider or "mock").strip().lower()
    if provider == "mock" or not cfg.api_key:
        return MockAIProvider(label="mock")
    if provider == "anthropic":
        from runtime.ai.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=cfg.api_key, model=cfg.model)
    endpoint = cfg.endpoint or "https://api.openai.com/v1/chat/completions"
    return OpenAICompatibleHttpProvider(api_key=cfg.api_key, endpoint=endpoint, model=cfg.model)
