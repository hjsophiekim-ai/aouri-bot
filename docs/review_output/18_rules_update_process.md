# 18. rules 운영본 갱신 프로세스(MVP)

## 1) 목적
- `review_rules_master.json`이 변경될 때 운영자가 안전하게 반영할 수 있도록 한다.
- 요구사항:
  - 새 json 검증
  - schema validation
  - 현재 운영본 백업
  - 새 운영본 교체
  - rules version 로그 기록(DB)
  - 실패 시 롤백

## 2) 구현 파일
- 스크립트: `scripts/update_rules.py`
- 대상 운영본(기본):
  - `aouri-bot/runtime/resources/review_rules_master.json`
- 백업 폴더:
  - `aouri-bot/runtime/resources/backup/`

## 3) 동작 개요
1. `--new`로 전달된 JSON 로드
2. `runtime/rules/schema.py` 기준 schema validation 수행
3. `--apply` 모드면:
   - 기존 운영본을 백업(타임스탬프 파일)
   - 임시 파일로 복사 후 무결성/재검증
   - 운영본 교체(atomic replace)
   - SQLite DB의 `rules_version_log`에 sha256 + schema_version 기록
4. 중간 실패 시:
   - 백업본으로 롤백 시도

## 4) 사용 예시
### 4.1 검증만(교체 없음)
```bash
python scripts/update_rules.py --new docs/review_output/04_review_rules_master.json
```

### 4.2 운영본 교체(+백업/로그)
```bash
python scripts/update_rules.py --new docs/review_output/04_review_rules_master.json --apply
```

### 4.3 다른 target에 적용(옵션)
```bash
python scripts/update_rules.py --new docs/review_output/04_review_rules_master.json --apply --target aouri-bot/runtime/resources/review_rules_master.json
```

## 5) 주의사항
- 스크립트는 rules JSON 파일 자체를 DB에 저장하지 않는다.
- DB에는 룰 버전 로그(sha256/schema_version)만 남긴다.
- 스키마 불일치 시 교체를 중단하며, 기존 운영본은 유지된다.

