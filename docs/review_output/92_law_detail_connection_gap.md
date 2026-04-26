# 국가법령정보 API 상세조회 연결 점검 (law/detail, precedent detail 등)

## 요약
- 결론: 상세조회(lawService.do) 관련 코드는 구현돼 있으나, 현재 review 흐름/API/UI에는 연결되어 있지 않다.
- 현재 런타임에서 사용되는 것은 “검색(lawSearch.do) 기반 목록” 중심이며, 상세(본문) 조회는 호출 경로가 없다.

## 1) 코드만 존재
- DRF 상세조회 메서드(법령/판례/해석례/행정규칙/자치법규)
  - [drf_client.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/drf_client.py#L50-L107)
    - `service()` (lawService.do)
    - `get_law_detail()`
    - `get_precedent_detail()`
    - `get_interpretation_detail()`
    - `get_admin_rule_detail()`
    - `get_local_ordinance_detail()`

## 2) 서비스에 연결됨
- 검색(목록)만 연결됨
  - [search_service.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L34-L120)
    - `search_for_review()` → target 5종에 대해 `LawDrfClient.search(...)` 호출
    - 내부적으로 `lawSearch.do`만 사용

## 3) API로 노출됨
- “검색 결과(law_search)”는 API 응답에 포함됨(상세조회는 미노출)
  - [server.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py#L561-L608): `/api/review/analyze` → `result["law_search"]`
  - [server.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py#L996-L1037): `/api/revision/suggest_text` → `law_search`
  - [server.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1062-L1115): `/api/questions/generate` → `law_search` 및 `law_topics` 반영
- 상세조회 전용 엔드포인트(예: `/api/law/detail`)는 현재 없음.

## 4) UI에서 사용 가능
- 현재 UI에서 “상세조회(lawService.do) 본문”을 클릭/확장해서 보여주는 기능은 확인되지 않음.
- 현재 UI 흐름은 `law_search`(목록/링크/식별자) 표시 또는 JSON 표시 수준으로 설계되어 있음(상세는 후속 과제로 남아 있음).

## 5) 아직 미구현(갭)
- 필요 기능(권장 순서)
  - “상세조회 API” 추가: `GET /api/law/detail?target=law&ID=...` 또는 `POST /api/law/detail`로 식별자 전달
  - 캐시/레이트리밋/에러 모델링: 본문은 길어서 캐시/요약 전략 필요
  - UI 패널: 목록(대표 3~5개) + “더보기” 클릭 시 상세(본문/요약) 로딩
