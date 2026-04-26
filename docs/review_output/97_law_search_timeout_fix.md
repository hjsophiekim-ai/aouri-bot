# law_search 타임아웃 제거(97)

## 목표
- “모든 정보 완전 연동”보다 “실제 응답이 안정적으로 나오는 것”을 우선한다.
- law_search는 optional enrichment로 유지하며, 실패해도 review 본체는 빠르게 응답해야 한다.

## 변경 전 증상
- `LAW_API_BASE_URL` 오설정(`open.law.go.kr`)로 DRF 호출이 404를 유발 가능
- 한 요청에서 토픽/타겟 호출이 많아 `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`가 지연/타임아웃 발생

## 변경 내용(핵심)
### 1) 토픽 수 제한
- 검색 토픽은 파생 목록 전체가 아니라 상위 3개까지만 사용
- 변경 코드: [search_for_review()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L23-L83)

### 2) 타겟 수 제한
- 타겟 5종(법령/판례/해석례/행정규칙/자치법규) 중, 성능 목표를 위해 우선 3종만 호출
  - 호출: 법령(law), 판례(prec), 해석례(expc)
  - 미호출: 행정규칙(admrul), 자치법규(ordin) → 빈 배열로 반환(스키마 유지)
- 변경 코드: [search_for_review()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L23-L83)

### 3) 상위 N개만 수집
- `max_per_type`는 최대 3으로 clamp(대표 3개 수준)
- 변경 코드: [search_for_review()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L23-L83)

### 4) per-call timeout 짧게 관리 + retry 제거
- UI/API 응답성을 위해 DRF 클라이언트 timeout을 3초 상한으로 제한하고 retry를 0으로 고정
- 변경 코드: [LawSearchService.__init__()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L23-L33)

### 5) target별 조기 종료
- 첫 토픽에서 충분히 모이면 추가 토픽 호출 생략(필요 최소 호출)
- 변경 코드: [_search_target()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L85-L120)

## 재검증(요약)
- `/api/review/analyze` 3케이스 모두 10초 이내 응답 + law_search 포함: [105_review_analyze_lawsearch_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/105_review_analyze_lawsearch_validation_rerun.md)
- `/api/questions/generate` 5케이스 모두 10초 이내 응답: [106_question_engine_law_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/106_question_engine_law_validation_rerun.md)
- `/api/revision/suggest_text` 10초 이내 응답 + law_search 포함: [107_revision_law_grounding_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/107_revision_law_grounding_validation_rerun.md)
