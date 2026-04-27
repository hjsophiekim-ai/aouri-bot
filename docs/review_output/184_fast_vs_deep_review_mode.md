# 184) fast mode / deep mode 분리

## 배경

- `/api/review/analyze`가 규칙 screening + 법령검색 + AI 정밀검토를 한 번에 수행하여, 사용자 체감 지연이 커질 수 있다.
- `/demo`는 “대기 화면이 멈춘 것처럼” 보이는 문제가 동시에 존재했다.

## 목표

- fast mode(5초 목표): 규칙 기반 screening, 핵심 조항/고위험 여부, 대표 결론을 빠르게 생성
- deep mode: clause-specific AI + law grounding + 조항별 수정 제안을 생성
- `/demo`는 fast 결과를 먼저 보여주고, deep 결과는 후속 로딩으로 갱신

## API 설계(현재 구현)

- 텍스트 기반
  - `POST /api/review/analyze_fast`: fast mode
  - `POST /api/review/analyze_deep`: deep mode
  - `POST /api/review/analyze`: 기본 deep 유지(호환), `review_mode=fast|deep` 또는 `fast_mode=true` 지원
- 세션 기반(업로드 플로우)
  - `POST /api/question_sessions/{id}/review_fast`: fast mode
  - `POST /api/question_sessions/{id}/review`: deep mode(기존)

## 구현 요약

- fast mode는 AI/Law를 강제 비활성화해 “빠른 1차 요약”을 반환한다.
- deep mode는 기존과 동일하게 AI/Law를 사용하되, 성능 최적화(185)로 호출 수를 제한한다.

## 구현 위치

- 서버: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - `_handle_review_analyze_api()`에서 fast/deep 분기 처리
- 세션: [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)
  - `run_review_with_session_fast()` 추가(세션 fast mode)

