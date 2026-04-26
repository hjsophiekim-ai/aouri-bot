# 템플릿 기반 초안 생성: AI 보강(선택)

## 목표
- 표준계약서 템플릿을 기본으로 사용(현 유지)
- AI는 문장 연결/표현 다듬기/안내 문구 보완만 담당
- 템플릿 없는 유형은 “초안 불가/기준 필요” 흐름 유지
- 자유 생성으로 전체 계약서를 무제한 생성하지 않음

## 동작 방식
1) 기존 `generate_draft_text()`로 템플릿 기반 초안 생성
2) OpenAI가 활성화되어 있으면
   - `draft_text`를 “표현만” 다듬음(조항 추가 금지)
   - 실패 시 원본 `draft_text` 유지

## 구현 위치
- Draft 생성 API: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- AI 보강 로직: [enhance.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/enhance.py) (`polish_draft_text`)
- 템플릿 기반 생성: [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)

## 응답 변화
- `draft_text`가 AI에 의해 다듬어진 버전으로 바뀔 수 있음
- `ai` 메타 필드가 포함될 수 있음(성공/실패 메타만)

