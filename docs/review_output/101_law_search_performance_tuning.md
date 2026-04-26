# law_search 성능 튜닝(101)

## 목표(요청 기준)
- `/api/review/analyze` 10초 내 응답
- `/api/questions/generate` 10초 내 응답
- `/api/revision/suggest_text` 10초 내 응답
- law_search 실패/빈 결과여도 본체 응답이 지연되지 않도록 optional enrichment로 유지

## 적용한 튜닝
- 토픽 수 제한: 상위 3개만 사용
- 타겟 수 제한: `law/prec/expc` 3종만 호출(나머지는 빈 배열로 반환해 스키마 유지)
- 상위 N개: 타겟별 최대 3개
- DRF timeout 짧게: 3초 상한 + retry=0
- 조기 종료: 타겟별 충분한 결과를 모으면 추가 토픽 호출 중단

## 변경 코드 위치
- 검색/수집 로직: [search_service.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L23-L120)
- 베이스 URL 교정: [config.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/config.py#L50-L92)

## 성능 재검증(실측)
- `/api/review/analyze` 3케이스: 모두 10초 이내 + law_search 포함  
  - [105_review_analyze_lawsearch_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/105_review_analyze_lawsearch_validation_rerun.md)
- `/api/questions/generate` 5케이스: 모두 10초 이내  
  - [106_question_engine_law_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/106_question_engine_law_validation_rerun.md)
- `/api/revision/suggest_text`: 10초 이내 + law_search 포함  
  - [107_revision_law_grounding_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/107_revision_law_grounding_validation_rerun.md)

## 해석(현 단계의 트레이드오프)
- 현재는 “안정적 응답”을 우선해 타겟/토픽을 제한한다.
- 행정규칙/자치법규까지 확장하려면
  - 캐시/쿼리 상한/조기 종료를 유지한 상태에서 타겟을 단계적으로 늘리는 방식이 안전하다.
