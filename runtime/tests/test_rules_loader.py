from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.rules.loader import DEFAULT_RULES_PATH, RuleLoader


class RuleLoaderTest(unittest.TestCase):
    def test_load_default_rules(self) -> None:
        loader = RuleLoader(DEFAULT_RULES_PATH)
        doc = loader.load()
        self.assertIn("rules_by_status", doc)
        self.assertIn("status_enum", doc)

    def test_invalid_rules_schema_raises(self) -> None:
        bad_doc = {"schema_version": "1.0", "rules_by_status": {}}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps(bad_doc, ensure_ascii=False), encoding="utf-8")
            loader = RuleLoader(p)
            with self.assertRaises(ValueError):
                loader.load()


if __name__ == "__main__":
    unittest.main()

