# 국가법령정보(DRF) 런타임 재검증(98)

## 재검증 범위
- DRF 직접 호출(법령/판례 검색)
- `/api/review/analyze`에서 `law_search` 포함 및 응답시간
- `/api/questions/generate`에서 `law_search`/토픽 반영 및 응답시간
- `/api/revision/suggest_text`에서 `law_search` 포함 및 응답시간
- `/demo`에서 결과 화면에 “관련 법령/판례/해석례”가 노출되는지

## 결과 요약
- DRF 직접 호출: PASS  
  - [104_law_api_runtime_check_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/104_law_api_runtime_check_rerun.md)
- `/api/review/analyze`: PASS(3 케이스 모두 10초 이내 + law_search 포함)  
  - [105_review_analyze_lawsearch_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/105_review_analyze_lawsearch_validation_rerun.md)
- `/api/questions/generate`: PASS(5 케이스 모두 10초 이내, 질문 배열 구조 확인)  
  - [106_question_engine_law_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/106_question_engine_law_validation_rerun.md)
- `/api/revision/suggest_text`: PASS(10초 이내 + law_search 포함)  
  - [107_revision_law_grounding_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/107_revision_law_grounding_validation_rerun.md)
- `/demo`: PASS(상세 보기에서 “관련 법령/판례/해석례” 노출)  
  - 재검증 문서: [108_demo_law_panel_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/108_demo_law_panel_validation_rerun.md)

## 남은 리스크(현 단계에서 허용)
- law_search는 성능 우선으로 “토픽/타겟/상위 N”을 제한 중이며, 행정규칙/자치법규는 현재 호출하지 않는다(빈 배열).
- UI는 현재 law_search를 “요약 카드”가 아니라 JSON 덤프 형태로 노출한다(표시 UX 개선 과제).
