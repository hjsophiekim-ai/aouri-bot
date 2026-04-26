# 국가법령정보 Open API client 구현 요약

가이드 출처:
- https://open.law.go.kr/LSO/openApi/guideList.do
- https://open.law.go.kr/LSO/openApi/guideResult.do

DRF 호출 베이스:
- `https://www.law.go.kr/DRF/lawSearch.do`
- `https://www.law.go.kr/DRF/lawService.do`

---

## 구현 파일

- Client (DRF 호출/파싱): [drf_client.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/drf_client.py)
- Config (env 로딩): [config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/config.py)
- Search service (review용 검색 조립 + 캐시): [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
- Cache (파일 기반): [cache.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/cache.py)

---

## 지원 기능 (요구사항 최소 충족)

- 키워드 기반 법령 검색
  - `LawDrfClient.search_laws(query=..., page=..., display=...)`
- 법령 상세(본문) 조회
  - `LawDrfClient.get_law_detail(ID 또는 MST...)`
- 판례 검색
  - `LawDrfClient.search_precedents(query=...)`
- 판례 상세(본문) 조회
  - `LawDrfClient.get_precedent_detail(precedent_id=...)`
- 해석례/행정규칙/자치법규 검색 및 상세 조회
  - 해석례: `search_interpretations` / `get_interpretation_detail` (`target=expc`)
  - 행정규칙: `search_admin_rules` / `get_admin_rule_detail` (`target=admrul`)
  - 자치법규: `search_local_ordinances` / `get_local_ordinance_detail` (`target=ordin`)

---

## 인증/보안 원칙

- API 키(OC)는 `LAW_API_KEY` 환경변수로만 읽고, 코드에 하드코딩하지 않습니다.
- 실패 메시지 반환 시에도 키 값은 포함하지 않습니다.

---

## timeout / retry / error handling

- `LawDrfClient`는 `timeout_sec`, `retry_count`를 받아 재시도합니다.
- 네트워크/HTTP 오류 시 `LawApiError(message, status_code, response_text)` 형태로 사람이 이해 가능한 메시지를 제공합니다.

---

## 응답 파싱

- `type=JSON` → JSON 파싱 후 `DrfResponse.json_obj`에 저장
- `type=XML` → XML 파싱 후 `DrfResponse.xml_root`에 저장
- `type=HTML` → raw_text 반환(본문 링크/미리보기 용도)

---

## aouribot 연동 지점

- `/api/review/analyze` 응답에 `law_search` 필드를 추가했습니다.  
- `/api/questions/generate`, `/api/revision/suggest_text`에도 `law_search`를 함께 반환합니다.

코드 위치:
- [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

