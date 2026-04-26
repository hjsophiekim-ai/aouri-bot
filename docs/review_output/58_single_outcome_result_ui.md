# /demo 결과 화면: 단일 대표 결론 중심 UI

## 목표
- 최종 결과는 하나의 대표 결론만 먼저 보여주기
- 이유 요약은 3~5줄
- 대표 추천 액션 1개를 명확히 표시
- 상세 내용은 펼침형(accordion)으로 숨기기

## 최종 구성
1) 대표 결론
- 예: “이 조항은 수정 제안을 권장합니다”
- 예: “이 계약은 표준 템플릿 기반 초안 작성이 적합합니다”
- 예: “위험도가 높아 법무 검토가 필요합니다”

2) 이유 요약(3~5줄)
- 주요 이슈(rule title)와 추천 템플릿 등을 간단히 노출

3) 대표 추천 액션 1개
- `대표 추천 액션: 수정 제안 확정` 또는 `대표 추천 액션: 초안 작성 확정`
- 추천 액션은 버튼의 primary/secondary 스타일로도 구분

4) 상세 보기(accordion)
- 검출 issue(요약)
- 적용 rule(원본)
- 수정 제안(원본 JSON)
- 추천 초안 템플릿/생성 결과(JSON)

## 대표 결론 결정 로직(MVP)
- `high_risk=true` 또는 `approval_required=true` → “법무 검토 필요”
- 그 외
  - 추천 템플릿이 있고 이슈가 적으면 → “초안 작성 추천”
  - 기본값 → “수정 제안 권장”

## 관련 코드
- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `buildResult()`에서 결론/요약/추천 액션/상세(JSON) 갱신

