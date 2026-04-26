# 12. Review 결과 저장(영속화) 설계/구현 (MVP)

## 1) 전제: 기존 DB 구조
- 현재 aouribot 레포에는 기존 DB/마이그레이션/ORM이 존재하지 않아 재사용할 “기존 테이블”이 없다.
- 따라서 새 프레임워크 없이 Python 표준 라이브러리 `sqlite3`로 **MVP 최소 스키마 + 코드 기반 마이그레이션**을 추가했다.

## 2) 저장 원칙
- rules 원본은 JSON 파일(`runtime/resources/review_rules_master.json`)을 기준으로 유지
- DB에는 “요청/결과/적용이력/이슈/룰 버전” 중심으로 저장
- 판정 결과는 `review analyze`의 raw JSON을 그대로 저장하여, 향후 스키마 확장 시 재가공 가능하게 함

## 3) DB 파일 위치
- DB 파일: `aouri-bot/runtime/data/db/aouribot.db`

## 4) 테이블(개념 매핑)
### 4.1 rules_version_log
- 목적: review 실행 시점에 어떤 rules 파일(version)이 적용됐는지 추적
- 키: `rules_sha256`

### 4.2 review_request
- 목적: 리뷰 요청 메타(법인/유형/파일명/소스/룰버전) 저장
- 저장 개념: `review_request`

### 4.3 review_result
- 목적: 단건 요청의 결과 저장(raw/summary + 집계 카운트)
- 저장 개념: `review_result`

### 4.4 review_applied_rule
- 목적: 매칭된 rule(적용 이력) 저장
- 저장 개념: `review_applied_rule`

### 4.5 review_issue
- 목적: 고위험/승인필요 등 운영상 “이슈”로 승격된 항목 저장
- 저장 개념: `review_issue`

## 5) 마이그레이션(스키마 변경)
- 구현 파일:
  - `aouri-bot/runtime/db/migrations.py`
- 방식:
  - `schema_migrations` 테이블에 적용 버전 기록
  - `CREATE TABLE IF NOT EXISTS` 기반으로 MVP 스키마 생성
  - 향후 컬럼 추가가 필요하면 `MIGRATIONS`에 버전 추가

## 6) 저장 로직(Repository/Service)
- 구현 파일:
  - `aouri-bot/runtime/db/review_repository.py`
- 주요 메서드:
  - `init_db()`: 마이그레이션 적용
  - `upsert_rules_version(...)`: rules version log 기록
  - `save_review(...)`: request/result/applied_rule/issue 저장
  - `list_requests(...)`: 목록 조회용
  - `get_review_detail(...)`: 상세 조회용

## 7) 저장 트리거(현재 MVP)
- Upload → Questions → Review 실행 시:
  - `POST /api/question_sessions/{id}/review` 호출 시 DB 저장 수행
- 직접 analyze 호출 시(옵션):
  - `POST /api/review/analyze` body에 `persist=true`를 넣으면 DB 저장

## 8) 이슈/적용룰 저장 기준(MVP)
- `review_applied_rule`: `matched_rules`에 포함된 rule을 저장
- `review_issue`: 아래 조건 중 하나면 issue로 저장
  - approval_required 매칭
  - risk_level이 high 계열(문자열 기준: high/very_high/critical)

