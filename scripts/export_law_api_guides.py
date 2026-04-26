from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runtime.law.guide_catalog import LawOpenApiGuideCatalog  # noqa: E402
from runtime.law.http import HttpClient  # noqa: E402


def main() -> None:
    http = HttpClient(timeout_sec=30.0, retry_count=1, user_agent="Mozilla/5.0")
    catalog = LawOpenApiGuideCatalog(http)
    gids = catalog.list_guide_ids()
    entries = []
    for gid in gids:
        e = catalog.fetch_guide_entry(gid)
        entries.append(
            {
                "guide_id": e.guide_id,
                "title": e.title,
                "request_url": e.request_url,
                "request_params": [{"name": p.name, "value": p.value, "description": p.description} for p in e.request_params],
                "change_log_lines": e.change_log_lines,
                "derived": e.derived,
            }
        )
    out_path = REPO_ROOT / "docs" / "review_output" / "law_openapi_guides.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"count": len(entries), "items": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()

