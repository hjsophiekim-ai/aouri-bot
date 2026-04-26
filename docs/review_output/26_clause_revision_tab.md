# 26. EP 패널 “계약서 수정 제안” 탭(MVP)

## 1) 목표
- 업로드된 계약서 텍스트 기준으로 rule 기반 이슈를 탐지하고, 조항별 “수정 제안 뷰”를 제공한다.
- MVP는 redline(문서 diff)까지 하지 않고, 화면에서 다음을 구조적으로 보여준다.
  - 원문 조항
  - 검출 이슈
  - 적용 rule
  - 추천 수정 방향
  - 대체 문안(fallback_text)
  - high risk 여부 / approval required 여부

## 2) API
- `POST /api/revision/suggest`
  - body: `{ "session_id": "<question_session_id>" }`
  - response:
    - `review_summary`
    - `revision.summary`
    - `revision.items[]`:
      - `original_clause`
      - `detected_issues[]`
      - `applied_rules[]`
      - `suggested_direction[]`
      - `fallback_text[]`
      - `high_risk`, `approval_required`

## 3) 서비스 구현
- 조항 분해:
  - `제N조` / `Article N` 패턴 기반으로 조항 블록 생성
  - 조항 헤더가 없으면 문단 단위로 chunking
- rule 매핑:
  - `matched_rules`의 `rule_id`별 키워드(TRIGGER_MAP/태그/대표문구)를 조항 텍스트에서 탐지
- 대체 문안/수정 방향:
  - `rule_id`별 `SUGGESTION_BY_RULE_ID`, `REPLACEMENT_TEXT_BY_RULE_ID` 매핑 제공
  - 매핑이 없는 룰은 향후 확장 대상(운영자가 rule에 “fallback_text”를 추가하는 방식으로 고도화 가능)

구현 파일:
- `aouri-bot/runtime/review/revision.py`
- `aouri-bot/runtime/api/server.py` (`/api/revision/suggest`)

## 4) UI(EP Mock)
- 탭: “계약서 수정 제안”
- 버튼: “수정 제안 불러오기”
- 구현 파일:
  - `aouri-bot/runtime/admin/ep_legal_request_ui.py`

## 5) MVP 한계/후속 고도화
- MVP 한계:
  - 실제 redline/문서 편집 없음(뷰만 제공)
  - 룰 매핑은 키워드 기반 단순 탐지(정교한 조항 파싱/위치 추적 미지원)
- 후속 고도화:
  - DOCX 템플릿 기반 redline 생성(조항 단위 삽입/삭제/대체)
  - 룰별 “대체 문안”을 rules JSON에 포함(운영자가 쉽게 관리)
  - EP 결재/법무 workflow와 연결(수정 제안 확인 완료 이벤트 기록)

