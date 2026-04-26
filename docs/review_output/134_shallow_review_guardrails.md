# 134. Shallow Review 재발 방지 Guardrails

## 목표
- “사용자 요약문/질문문만 분석 → generic result”로 회귀하는 문제를 방지
- 업로드 계약서 본문이 있으면 반드시 그것을 최우선으로 사용
- 원문/조항이 부족하면 경고 및 docx 생성 차단

## 적용된 Guardrail
### 1) 업로드 계약서 본문 우선 분석
- 업로드 기반 `/demo`는 세션 기반 흐름(`/api/question_sessions/{id}/review`)으로 통일
- 업로드 추출 텍스트는 세션의 `text`에 저장되며, 이후 분석은 이 값을 사용
- 위치: [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py), [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)

### 2) 사용자 설명문은 보조 context로만 사용
- 업로드 기반에서는 분석 입력(text)을 UI에서 직접 구성하지 않고(덮어쓰기 방지), 세션의 본문을 사용
- 질문 답변(answers)은 `text`를 덮어쓰지 않고 보조 정보로만 저장/전달

### 3) 원문 텍스트 길이가 짧으면 경고
- `contract_text_too_short_warning` 등 warnings를 `meta.warnings`로 반환
- 구현: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 4) clause extraction 실패 시 fallback 경고
- 조항 헤딩 패턴이 없어서 문단형(P-xxx)로만 분리되면 `clause_extraction_fallback_warning`
- 조항이 전혀 생성되지 않으면 `clause_extraction_failed` 및 docx 차단

### 5) summary text만으로 docx 생성 금지
- `meta.docx_allowed=false`인 경우 docx 다운로드 요청을 400으로 차단
- 차단 조건(요지)
  - 본문이 너무 짧음
  - 조항이 없음/조항 구조가 부족함
  - 헤딩 기반 조항이 없고(요약문 가능성) 조항 수가 매우 적은 경우
- 구현: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py), [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## UI 반영
- 결과 화면에서 docx 생성 가능 여부를 표시하고, 생성 불가 시 다운로드 버튼을 비활성화
- 위치: [internal_demo_chat_ui.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
