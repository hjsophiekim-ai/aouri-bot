# 다음 개발 단계 실행 계획(현 상태 기준, 과장 없음)

## 0) 현재 관측된 핵심 이슈
- OpenAI: `OPENAI_API_KEY` 미설정으로 mock 상태( [86](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/86_env_runtime_validation.md), [87](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/87_openai_health_runtime_check.md) )
- 법령(DRF): `LAW_API_ENABLED=true` + 키 인식은 되지만, base_url이 `https://open.law.go.kr`로 인식되며 DRF 호출이 HTTP 404( [88](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/88_law_api_runtime_check.md) )
- 성능/UX: law_search가 포함된 엔드포인트들이 25초 내 응답 불가(타임아웃 반복)( [89](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/89_review_analyze_lawsearch_validation.md), [90](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/90_question_engine_law_validation.md), [91](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/91_revision_law_grounding_validation.md) )

## 1) 지금 당장 해야 할 것(우선순위 High)
### 1-1. 환경변수/런타임 검증 완료
- 목표: “설정이 맞으면 즉시 성공/실패가 드러나는” 상태 확보
- 액션
  - `.env`의 `LAW_API_BASE_URL`을 DRF 베이스(`https://www.law.go.kr/DRF`)로 교정 여부 확인
  - `/api/ai/health`로 OpenAI 활성 여부를 단일 진실 소스로 고정(이미 있음)
  - `/api/law/health` 같은 간단한 DRF 헬스체크(법령 1회 검색) 엔드포인트 추가 여부 검토(있으면 운영 점검이 쉬워짐)

### 1-2. law_search “실응답” 확인
- 목표: `/api/review/analyze`에서 law_search가 “성공 파싱된 목록”을 포함
- 액션
  - DRF base_url 교정 후, 샘플 키워드(대리점법 등)로 `law`/`prec` 검색이 200 + JSON 파싱 성공하는지 확인
  - 실패하면 원인을 유형화(인증/도메인·IP 제한/timeout/형식 변경)하고 운영 가이드에 반영

### 1-3. law_search 성능 개선(타임아웃 제거)
- 목표: 질문/검토/수정 제안 API가 “수 초 내” 응답(법령 API 장애여도 degrade)
- 액션(코드 변경 후보)
  - 쿼리 수 제한: `queries[:N]` 형태로 상한 도입(법인 우선 토픽이 많아도 N개까지만)
  - 조기 종료: target별로 충분한 결과가 모이면 남은 쿼리 호출 생략
  - timeout/retry를 “엔드포인트별”로 다르게(예: UI 경로는 더 공격적으로 짧게)
  - 실패 시: law_search는 `enabled=true`라도 결과는 빈 배열 + 오류만 반환(핵심 기능은 계속)

## 2) 다음에 해도 되는 것(우선순위 Medium)
### 2-1. 상세조회 API 추가 여부 결정
- 선택지 A(권장): “목록 + 더보기(상세)” UX를 위해 상세조회 API(`/api/law/detail`) 추가
- 선택지 B: MVP는 목록/링크까지만 노출하고 상세는 외부 링크로 대체

### 2-2. 상세조회 UI/패널 연결
- 목록(대표 3~5개) + “더보기” 클릭 시 상세(본문/요약) 로딩
- 캐시/요약 전략 포함(본문은 길고 호출 비용이 큼)

### 2-3. OpenAI + 법령검색 결합 설명 고도화
- OpenAI 활성 시에도 “법령 근거 없는 단정”을 금지하는 프롬프트/출력 정책 강화
- law_search 실패 시에는 근거 없는 문장 생성 대신 템플릿 기반 설명으로 degrade

## 3) EP 연동 준비(우선순위 Medium~Low, 전제조건 있음)
- 전제: `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`가 안정적으로 응답하고(타임아웃 없음) 결과 스키마가 고정되어야 함
- 액션
  - EP에서 필요로 하는 최소 필드 세트 정의(요약/승인필요/근거/링크)
  - 운영 환경에서 DRF IP/도메인 등록 이슈를 사전에 해결
