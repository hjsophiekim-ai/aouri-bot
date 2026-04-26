# /api/revision/suggest_text: AI 문구 보강(선택)

## 목표
- 최종 판정은 기존 confirmed rule 기반 유지
- AI는 “설명문/추천 수정문안” 표현을 다듬는 역할만 수행
- 적용 rule, risk_level, approval_required 구조는 유지
- AI 실패 시 기존 fallback_text/추천 방향을 그대로 사용

## 동작 방식
1) 기존 로직으로 review analyze + revision suggest 생성(rule 기반)
2) OpenAI가 활성화되어 있으면
   - `recommended_rewrite`, `suggested_direction`만 다듬음
   - 실패 시 원본 revision 그대로 반환

## 구현 위치
- API 핸들러: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- AI 보강 로직: [enhance.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/enhance.py) (`polish_revision`)

## 응답 변화
- 응답에 `ai` 필드가 추가될 수 있음(성공/실패 메타만)

