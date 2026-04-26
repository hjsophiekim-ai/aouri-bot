# 06. Rules Loader 구현 요약

## 구현 범위
- rules 저장 위치 확정:
  - 런타임 탑재본: `aouri-bot/runtime/resources/review_rules_master.json`
  - 원본 분석 산출물: `docs/review_output/04_review_rules_master.json`
- schema validation + loader + 판정/백로그 분리 로딩 구현

## 생성/수정 파일
- `aouri-bot/runtime/rules/schema.py`
- `aouri-bot/runtime/rules/loader.py`
- `aouri-bot/runtime/resources/review_rules_master.json` (탑재본 복사)

## 핵심 동작
- `schema.py`
  - 상태 enum 강제:
    - `confirmed_standard`
    - `confirmed_pattern`
    - `exception_possible`
    - `approval_required`
    - `unconfirmed_backlog`
  - 각 rule 필수 필드 검증:
    - `rule_id, entity, contract_type, clause_type, rule_level, title, description, contract_evidence, risk_level, review_action, approval_required, tags`
- `loader.py`
  - 기본 로딩 경로:
    - `runtime/resources/review_rules_master.json`
  - `load()` 시 스키마 검증 실패하면 예외 발생(서비스 시작 차단)
  - `decision_rules()`는 `unconfirmed_backlog` 제외
  - `backlog_rules()`는 참고용으로 별도 제공

## 정책 반영 여부
- CONFIRMED 기반 rule만 판정 대상: 반영 완료
- unconfirmed_backlog 참고용 분리: 반영 완료

