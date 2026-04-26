# 조항별 수정 제안 엔진 v2 (설명 가능한 뷰 품질 개선)

## 목표
- 원문 조항 + 검출 issue + 적용 rule + (fallback_text/추천 수정문안) + approval required 여부를 한 화면에서 보기 좋게 제공
- redline 자동 생성은 제외(아직)

## 변경 사항 요약
기존 v1의 “조항별 매칭 + 대체 문안 목록”에 더해, v2는 아래를 강화했다.
- 조항별로 어떤 키워드가 매칭되었는지(`matched_keywords`)를 제공(설명가능성 강화)
- 각 이슈에 대해 rule의 `review_action`을 함께 제공(수정 방향을 구체화)
- `recommended_rewrite`를 추가(가능할 때 1개 대표 대체문안)
- 결과 정렬을 “approval_required → high_risk → clause_id” 우선순위로 고정(리뷰 효율)

## 구현 코드
- 엔진: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
  - `suggest_revisions()` 결과 항목 확장
  - `recommended_rewrite`, `match_evidence`, `review_action`, `matched_keywords` 추가
- API:
  - 세션 기반: `POST /api/revision/suggest` (기존 유지)
- UI(EP Mock):
  - [ep_legal_request_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/ep_legal_request_ui.py)

## 출력 스키마(v2)
`revision.items[]` 항목에 추가된 필드:
- `applied_rules[].matched_keywords`: 해당 조항에서 실제로 발견된 트리거 키워드 목록
- `detected_issues[].review_action`: rule에서 제공하는 권장 조치 리스트
- `match_evidence[]`: rule_id와 matched_keywords 요약(렌더링 단순화용)
- `recommended_rewrite`: 대표 대체 문안 1개(가능한 경우)

요약 필드 추가:
- `summary.recommended_rewrite_clause_count`

## MVP 운용 가이드
- `recommended_rewrite`는 “대체 문안 후보”이며 자동 반영이 아니라 **검토자 확인용**이다.
- `review_action`은 실제 협상/수정 체크리스트로 활용한다.
- 키워드 기반이므로, “문맥 반대(부정/예외/정의)”에는 오탐 가능성이 있어 후속 고도화 대상이다.

