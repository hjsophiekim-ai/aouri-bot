from __future__ import annotations

import os
import unittest

from runtime.ai.config import load_ai_config
from runtime.ai.factory import create_ai_provider


class AIConfigTest(unittest.TestCase):
    def test_env_config_loads(self) -> None:
        old = dict(os.environ)
        try:
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            os.environ["OPENAI_MODEL"] = "gpt-4.1-mini"
            os.environ["OPENAI_TIMEOUT"] = "3"
            os.environ["OPENAI_MAX_TOKENS"] = "123"
            os.environ["OPENAI_TEMPERATURE"] = "0.7"
            cfg = load_ai_config()
            self.assertEqual(cfg.provider, "mock")
            self.assertEqual(cfg.model, "gpt-4.1-mini")
            self.assertEqual(cfg.timeout_sec, 3.0)
            self.assertEqual(cfg.max_tokens, 123)
            self.assertAlmostEqual(cfg.temperature, 0.7, places=3)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_factory_returns_mock_without_key(self) -> None:
        old = dict(os.environ)
        try:
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            p = create_ai_provider()
            self.assertTrue(hasattr(p, "complete"))
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()

