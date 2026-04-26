from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aouri-bot"))

from runtime.db.review_repository import ReviewRepository
from runtime.rules.schema import validate_rules_document


def _utc_now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha_file(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, help="path to new rules json")
    ap.add_argument(
        "--target",
        default=str(Path("aouri-bot") / "runtime" / "resources" / "review_rules_master.json"),
        help="target rules path (default: aouri-bot/runtime/resources/review_rules_master.json)",
    )
    ap.add_argument("--apply", action="store_true", help="apply update (otherwise validate only)")
    args = ap.parse_args()

    new_path = Path(args.new)
    if not new_path.exists():
        print(f"new rules not found: {new_path}")
        return 2

    try:
        doc = json.loads(new_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"failed to read json: {exc}")
        return 2

    errors = validate_rules_document(doc if isinstance(doc, dict) else {})
    if errors:
        print("schema validation failed:")
        for e in errors:
            print(f"- {e}")
        return 1

    print("schema validation: OK")
    schema_version = str(doc.get("schema_version", "unknown"))
    new_sha = _sha_file(new_path)
    print(f"new rules sha256: {new_sha}")
    print(f"schema_version: {schema_version}")

    if not args.apply:
        print("validate-only mode. use --apply to update runtime rules.")
        return 0

    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = target.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    tag = _utc_now_tag()
    backup_path = backup_dir / f"review_rules_master_{tag}.json"
    rollback_path = None

    try:
        if target.exists():
            shutil.copy2(target, backup_path)
            rollback_path = backup_path
            print(f"backup created: {backup_path}")

        tmp_path = target.parent / f".review_rules_master_{tag}.tmp"
        shutil.copy2(new_path, tmp_path)
        tmp_sha = _sha_file(tmp_path)
        if tmp_sha != new_sha:
            raise RuntimeError("integrity check failed after copy")

        tmp_doc = json.loads(tmp_path.read_text(encoding="utf-8"))
        tmp_errors = validate_rules_document(tmp_doc if isinstance(tmp_doc, dict) else {})
        if tmp_errors:
            raise RuntimeError("schema validation failed after copy")

        tmp_path.replace(target)
        print(f"rules updated: {target}")

        repo = ReviewRepository()
        repo.init_db()
        repo.upsert_rules_version(new_sha, schema_version, str(target))
        print("rules version logged to DB")
        return 0
    except Exception as exc:
        print(f"update failed: {exc}")
        if rollback_path and rollback_path.exists():
            try:
                shutil.copy2(rollback_path, target)
                print(f"rollback applied from backup: {rollback_path}")
            except Exception as rex:
                print(f"rollback failed: {rex}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

