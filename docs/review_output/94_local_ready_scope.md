# 로컬 실사용 테스트 가능 범위(현 상태 기준)

## 1) 지금 바로 가능
- 기본 서버 구동 및 기본 페이지 접근(`/admin`, `/upload`, `/demo`)
- OpenAI 비활성(mock) 상태에서의 기본 동작 확인
  - `/api/ai/health`가 `enabled=false, provider=mock`으로 정상 응답( [87_openai_health_runtime_check.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/87_openai_health_runtime_check.md) )

## 2) 설정만 하면 가능
- OpenAI 실제 활성화
  - 필요: `.env`에 `OPENAI_API_KEY` 설정(값 미노출 원칙 준수)
  - 성공 기준: `/api/ai/health`에서 `enabled=true, provider=openai` 및 `elapsed_sec` 확인
  - 현 상태: `OPENAI_API_KEY` 미감지로 mock( [86_env_runtime_validation.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/86_env_runtime_validation.md) )
- 국가법령정보(DRF) 검색이 “성공”하는 상태
  - 현 상태: `LAW_API_ENABLED=true` 및 `LAW_API_KEY`는 로더가 인식하나, DRF 호출이 HTTP 404( [88_law_api_runtime_check.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/88_law_api_runtime_check.md) )
  - 우선 확인: `LAW_API_BASE_URL`이 `https://www.law.go.kr/DRF` 형태인지

## 3) 추가 구현 필요
- 국가법령정보 상세조회(lawService.do) 결과를 실제 리뷰 흐름/UI에서 “클릭/확장”으로 볼 수 있게 하는 기능
  - 현재는 상세조회 메서드만 존재하고 API/UI 연결이 없음( [92_law_detail_connection_gap.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/92_law_detail_connection_gap.md) )
- law_search 품질/성능 제어(쿼리 수 제한, 조기 종료, 실패 시 빠른 degrade)
  - 현재 `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`가 25초 내 응답을 주지 못해 타임아웃 관측( [89](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/89_review_analyze_lawsearch_validation.md), [90](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/90_question_engine_law_validation.md), [91](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/91_revision_law_grounding_validation.md) )

## 4) EP 연동 전 추천 범위
- “룰 기반 검토 + 질문 + 수정 제안”의 핵심 플로우를 안정화
- 법령 검색은
  - (a) 완전히 비활성(LAW_API_ENABLED=false)로 성능 리스크 제거 후 데모,
  - 또는 (b) base_url/쿼리 제한/캐시가 정리된 뒤 단계적 재도입

## 5) 법무팀 내부 데모 가능 범위
- OpenAI 없이(mock)도 룰 기반 결과/질문/수정 제안이 “끊기지 않고” 나오는 데모
- 법령 근거 패널은 현재 상태에선 “실근거” 데모가 어려움
  - DRF 호출이 404로 실패하며(설정 이슈), 관련 엔드포인트 응답도 지연/타임아웃이 발생함
