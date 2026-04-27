# 178) 필수/권장/참고 3단계(three-tier) 출력 체계 반영

## 목표
- 필수수정(HIGH): 반드시 redline(본문 수정)
- 권장수정(MEDIUM): blue guidance(방향/사유 중심, 필요 시 선택 수정)
- 참고제안(LOW): 참고 메모(기본 숨김 가능, 본문 미수정 원칙)

## 구현 요약
- clause 결과에 3단계 필드 추가
  - `must_fix`: HIGH/approval_required 기반 boolean
  - `review_tier`: `MUST | SUGGEST | NOTE`
- AI deep review는 `risk_tier/must_fix`를 입력값 그대로 유지하도록 프롬프트에 명시(출력 일관성)

관련 코드:
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 출력 반영 위치
- Review API(`/api/review/analyze`): `clause_results[]`에 `risk_tier/must_fix/review_tier` 포함
- Session review(`/api/question_sessions/{id}/review`): analyze와 동일한 구조로 AI/Law 반영 + 동일 필드 유지
- Word(DOCX): 본문 redline(HIGH) / guidance(MEDIUM/LOW) 분리 유지(legend 추가는 179 참고)

