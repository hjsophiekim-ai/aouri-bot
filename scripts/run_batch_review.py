from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aouri-bot"))

from runtime.db.review_repository import ReviewRepository
from runtime.rules.loader import RuleLoader
from runtime.review.classify import classify
from runtime.services.query_service import ReviewInput, RuleQueryService


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input-dir",
        default=str(Path("docs") / "review_output" / "02_extracted_texts"),
        help="extracted texts directory (default: docs/review_output/02_extracted_texts)",
    )
    ap.add_argument("--dry-run", action="store_true", help="do not write DB, only print summary")
    ap.add_argument(
        "--output-jsonl",
        default=str(Path("docs") / "review_output" / f"15_batch_review_results_{_now_tag()}.jsonl"),
        help="output jsonl path",
    )
    ap.add_argument(
        "--fail-log",
        default=str(Path("docs") / "review_output" / f"15_batch_review_failures_{_now_tag()}.log"),
        help="failure log path",
    )
    ap.add_argument("--limit", type=int, default=0, help="limit number of files (0 = no limit)")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"input dir not found: {input_dir}")
        return 2

    loader = RuleLoader()
    rules_doc = loader.load()
    service = RuleQueryService(loader)
    repo = ReviewRepository()
    repo.init_db()

    files = sorted([p for p in input_dir.rglob("*.txt") if p.is_file()])
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    ok = 0
    fail = 0

    out_jsonl = Path(args.output_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    fail_log = Path(args.fail_log)
    fail_log.parent.mkdir(parents=True, exist_ok=True)

    with out_jsonl.open("w", encoding="utf-8") as out, fail_log.open("w", encoding="utf-8") as flog:
        for p in files:
            try:
                text = _read_text(p)
                cls = classify(None, None, text, p.name, file_path=str(p))
                review = service.analyze(
                    ReviewInput(
                        entity=cls.entity,
                        contract_type=cls.contract_type,
                        text=text,
                        filename=p.name,
                        answers={},
                    )
                )
                record = {
                    "file": str(p),
                    "entity": cls.entity,
                    "contract_type": cls.contract_type,
                    "entity_source": cls.entity_source,
                    "contract_type_source": cls.contract_type_source,
                    "is_inferred": cls.is_inferred,
                    "summary": review.get("summary", {}),
                }

                if not args.dry_run:
                    persisted = repo.save_review(
                        entity=cls.entity,
                        contract_type=cls.contract_type,
                        filename=p.name,
                        source="batch_extracted_texts",
                        question_session_id=None,
                        rules_sha256=sha256(Path(loader.rules_path).read_bytes()).hexdigest(),
                        rules_schema_version=str(rules_doc.get("schema_version", "unknown")),
                        rules_source_path=str(loader.rules_path),
                        review_result=review,
                        text=text,
                    )
                    record["request_id"] = persisted.request_id
                    record["rules_sha256"] = persisted.rules_sha256

                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                ok += 1
            except Exception as exc:
                flog.write(f"{p}\t{exc}\n")
                fail += 1

    print(f"batch done: ok={ok} fail={fail} dry_run={args.dry_run}")
    print(f"jsonl: {out_jsonl}")
    print(f"fail_log: {fail_log}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

