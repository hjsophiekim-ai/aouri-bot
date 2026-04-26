# 07. Review Analyze API 구현 요약

## 구현 범위
- rule query service + review analyze API 구현
- HTTP 서버는 Python 표준 라이브러리(`http.server`) 기반으로 구성
- 새 프레임워크 도입 없음

## 생성/수정 파일
- `aouri-bot/runtime/services/query_service.py`
- `aouri-bot/runtime/api/server.py`
- `aouri-bot/runtime/app.py`

## API 엔드포인트
- `GET /health`
  - 서버 상태 확인
- `GET /api/rules?status=&entity=&contract_type=`
  - 판정 대상 rules 조회(`unconfirmed_backlog` 제외)
- `GET /api/backlog`
  - backlog 참고용 조회(판정 로직 미사용)
- `POST /api/review/analyze`
  - 입력: `entity`, `contract_type`, `text`, `filename(optional)`
  - 출력:
    - `matched_rules`
    - `checklist_rules`
    - `approval_required_matches`
    - `backlog_reference_only`
    - `summary`

## 판정 로직(MVP)
- 적용 대상: `confirmed_standard`, `confirmed_pattern`, `exception_possible`, `approval_required`
- 제외 대상: `unconfirmed_backlog`(참고 전용)
- 매칭 방식:
  - 룰 ID별 트리거 키워드(`TRIGGER_MAP`) 기반 텍스트 포함 여부 매칭
  - 트리거 없는 룰은 체크리스트 항목으로 반환

## 정책 반영 여부
- CONFIRMED 기반 rule만 판정: 반영 완료
- backlog는 참고용 표시만: 반영 완료

