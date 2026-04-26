# /demo 화면 법률 검색 패널 노출 검증

## 결론(현재 로컬 기준)
- `/demo` 페이지 로딩 및 입력 폼 노출은 확인됨.
- “질문 흐름(답변 입력/다음)” 관련 UI 요소는 접근성 트리에서 확인되지만, 화면(스크린샷)에서는 입력 폼(검토 시작 버튼)이 계속 보여 “상태 전환이 시각적으로 일관되지 않음”이 관측됨.
- 결과 화면(법령/판례 패널 포함)까지 도달해 패널을 확인하는 것은 이번 런에서 실패했다.
  - 원인 후보: `/api/questions/generate` 및 관련 법령 검색 흐름이 느리거나 타임아웃(별도 런타임 검증 문서에서 25초 타임아웃 반복 관측).

## 확인 항목별 결과
### 1) 계약 입력 후 결과 화면에 법령/판례 패널이 보이는지
- FAIL(결과 화면까지 도달/렌더 확인 불가)

### 2) 대표 3~5개 정도 요약 노출이 되는지
- FAIL(결과 패널 미도달)

### 3) 링크/식별정보가 보이는지
- FAIL(결과 패널 미도달)

### 4) UI가 너무 복잡하지 않은지
- PARTIAL
  - 입력 단계 UI는 단순(법인/계약유형/텍스트 + 검토 시작).
  - 이후 단계(질문/결과)는 시각적 상태 전환이 일관되지 않아 사용자가 “진행 중인지/어디에 있는지” 혼란 가능성이 있음.

### 5) law_search가 빈 경우 fallback 문구가 있는지
- FAIL(결과 패널 미도달로 확인 불가)

## 근거(관측)
- `/demo` 진입 시 입력 폼 요소(법인/계약유형/텍스트/검토 시작 버튼) 확인
- 브라우저 네트워크 요청에서 `POST /api/questions/generate`가 발생하는 것 확인
- 동일 런타임에서 `/api/questions/generate`는 별도 검증에서 25초 내 응답을 받지 못해 타임아웃( [90_question_engine_law_validation.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/90_question_engine_law_validation.md) )

## 다음 조치(재검증을 위한 최소 조건)
- LAW API의 base_url/성능 이슈를 해결해 `/api/questions/generate`가 수 초 내 응답하도록 만든 뒤, `/demo`에서 결과 화면까지 재검증한다.
  - 현 상태에서 LAW API base_url이 `https://open.law.go.kr`로 인식되며 DRF 호출이 HTTP 404로 실패( [88_law_api_runtime_check.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/88_law_api_runtime_check.md) )
