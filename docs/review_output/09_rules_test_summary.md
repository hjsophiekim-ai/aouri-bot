# 09. Rules MVP 테스트 요약

## 테스트 코드
- `aouri-bot/runtime/tests/test_rules_loader.py`
- `aouri-bot/runtime/tests/test_query_service.py`
- `aouri-bot/runtime/tests/test_api_server.py`

## 실행 명령
```bash
cd aouri-bot
python -m unittest discover -s runtime/tests -v
```

## 실행 결과
- 총 7개 테스트 통과
  - `test_health` OK
  - `test_review_analyze` OK
  - `test_analyze_detects_approval_required_rules` OK
  - `test_backlog_reference_only` OK
  - `test_decision_rules_exclude_backlog` OK
  - `test_invalid_rules_schema_raises` OK
  - `test_load_default_rules` OK

## 검증 포인트
- 스키마 검증 실패 시 로더 예외 처리 확인
- 판정 rules에서 backlog 제외 정책 확인
- review analyze에서 승인 필요 룰 탐지 확인
- API health/analyze 엔드포인트 동작 확인

