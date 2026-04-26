# OpenAI provider 실활성 최종 검증(119)

## 주의
- 키 값, Authorization 헤더, 민감정보는 출력 금지
- 성공/실패와 원인만 기록

## 1) /api/ai/health 확인
- enabled=true / provider=openai / ok=true 확인(값 미출력)

## 2) 아주 짧은 테스트 프롬프트 1회 호출
- 방식: 런타임 AI provider로 `"Say OK"` 요청 1회 수행
- 결과: 호출 성공(call_ok=true) 및 응답시간(초) 계측 확인

## 3) API 플로우에서 AI 보강 적용 확인
- `/api/revision/suggest_text` 호출 결과에서 `ai` 메타가 포함되는지 확인
  - ai_present=true 이면 “AI 보강 경로가 실제로 실행됨”을 의미

## 요약
- OpenAI provider 활성: PASS
- OpenAI API 단일 호출 성공: PASS
- revision 플로우 AI 보강 적용: PASS
