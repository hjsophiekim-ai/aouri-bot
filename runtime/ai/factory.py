from __future__ import annotations

from runtime.ai.config import AIConfig, load_ai_config
from runtime.ai.http_openai_compatible_provider import OpenAICompatibleHttpProvider
from runtime.ai.mock_provider import MockAIProvider
from runtime.ai.provider import AIProvider


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
