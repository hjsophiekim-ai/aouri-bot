# 국가법령정보 Open API 연동 아키텍처 (aouribot)

목표: rule engine + OpenAI(선택) + 국가법령정보 Open API(DRF)를 결합해, 계약서 검토 결과에 “최신 법령/판례/해석례” 근거를 함께 제시합니다.

본 설계는 현재 aouribot 구조(표준 라이브러리 기반 HTTP 서버, `RuleQueryService.analyze`, `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`, `/demo`)를 기준으로 합니다.

---

## 1) Law API client를 둘 레이어

- **infra(adapter) 레이어**: `runtime/law/drf_client.py`
  - DRF 호출(`lawSearch.do`, `lawService.do`) + 포맷(JSON/XML/HTML) 파싱 + timeout/retry/error 처리
- **domain service 레이어**: `runtime/law/search_service.py`
  - “계약 검토에 필요한 검색”을 제품 관점으로 캡슐화(어떤 target을 어떤 쿼리로, 몇 개까지, 어떤 TTL로)
  - aouribot의 rule 결과/계약유형/키워드를 받아서 “법률 근거 묶음(law_search)”을 만든다.
- **API handler 레이어**: `runtime/api/server.py`
  - `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`에서 `law_search`를 함께 반환

---

## 2) Search service / Lookup service 분리 여부

- **분리(권장)**:
  - `SearchService`: 키워드 기반 목록 검색 (lawSearch)
  - `LookupService`: 선택 항목의 본문/상세 조회 (lawService)
- 현재 구현은 1차로 **Search 중심**(review 결과에 “대표 3~5개 요약”)을 만족하도록 구성하고, “더보기/상세”가 필요해지면 Lookup을 추가하는 구조로 설계합니다.

근거:
- 가이드 상에서 검색(`lawSearch`)과 본문(`lawService`)이 URL/파라미터 레벨로 명확히 분리되어 있음.

---

## 3) review analyze 시 자동 법령 검색 흐름

- 입력: 계약 텍스트 + entity + contract_type + answers + rule 매칭 결과
- 흐름:
  1. 기존 `RuleQueryService.analyze(...)` 수행 (deterministic)
  2. 결과의 `matched_rules`, `contract_type`, `text`를 기반으로 “검색 토픽/쿼리” 도출
  3. 국가법령정보 API(DRF)로 target별 검색 실행:
     - 법령: `target=law`, 필요 시 `target=eflaw`
     - 판례: `target=prec`
     - 해석례: `target=expc` (+ 부처별 해석은 후순위로 확장)
     - 행정규칙: `target=admrul`
     - 자치법규: `target=ordin`
  4. 결과를 `law_search`로 정규화하여 review 응답에 포함

- 실패/비활성화 시:
  - `law_search.enabled=false` + `note/error`로 “왜 근거가 없는지”를 명확히 반환

---

## 4) question flow와 법령 검색 연결 방식

목표는 “법률상 중요한 추가 질문을 더 잘 뽑게” 하는 것입니다.

- 기본은 기존 rule 기반 질문 생성 유지
- 법령검색이 가능하면:
  - 검색 토픽(예: “대리점법”, “하도급법”, “개인정보보호법”)을 질문 엔진에 입력으로 전달
  - 질문 엔진은 토픽에 매핑된 **추가 질문 세트**를 덧붙임
  - AI(OpenAI)가 있으면 질문 표현만 다듬고(결론/판정은 rule 기반 유지)

현재 구현 연결:
- `/api/questions/generate`가 `law_search.queries`를 받아 `generate_questions(..., law_topics=...)`에 전달.

---

## 5) revision suggestion과 법령 근거 연결 방식

- `/api/revision/suggest_text`는 이미 rule 기반 `review_summary + revision`을 생성함
- 여기에 `law_search`를 함께 반환해서:
  - “어떤 조항이 왜 위험인지” 설명을 할 때, 관련 법령/판례/해석례 목록을 근거로 함께 제시 가능
- AI(OpenAI)가 활성화되면:
  - 수정 제안 문안/설명문을 자연어로 보강하되,
  - `law_search`가 없으면 “근거 없는 단정”을 피하도록 제한

---

## 6) 결과 화면에서 출처 표시 방식

UI 원칙:
- 기본은 “대표 3~5개”만 노출(과도한 정보 노이즈 방지)
- 각 항목은 아래 정보를 갖도록 정규화
  - title
  - snippet(짧은 요약)
  - target(법령/판례/해석례/행정규칙/자치법규)
  - identifiers(ID/MST 등)
  - drf_detail_url(가능하면)

현재 데모 UI(`/demo`) 반영:
- 결과 상세 보기(accordion) 안에 “관련 법령/판례/해석례” JSON을 노출(간단 구현)
- 추후: 카드/탭 형태로 요약 UI를 별도 구성(80번 요구사항 단계)

---

## 7) 캐싱 전략

목표: 같은 계약/같은 질문에서 반복 호출 최소화

- 캐시 키:
  - `base_url + target + query + page + display + fmt`
  - JSON 정렬 후 sha256으로 키 생성
- TTL:
  - 검색 결과는 6시간(초기값)으로 시작
  - “법령 최신성/업데이트 민감도”가 높은 주제는 TTL을 더 낮게 조정 가능
- 저장소:
  - MVP에서는 파일 기반 JSON 캐시(`runtime/data/law_cache.json`)
  - 운영/다중 인스턴스에서는 DB/Redis로 확장 가능

---

## 8) 실패 시 fallback 전략

실패는 크게 3종으로 나눠 처리합니다.

- **기능 비활성화**: `LAW_API_ENABLED=false` 또는 `LAW_API_KEY` 없음
  - 검색을 시도하지 않고 `enabled=false`로 명확히 반환
- **인증/화이트리스트 오류**: DRF 응답에서 “IP/도메인 등록 필요” 류 메시지 발생 가능
  - `enabled=false`로 강등하지 않고, 호출 결과에 `error`로 표기(운영 설정 이슈로 분리)
- **일시 장애/네트워크 오류**
  - retry 후 실패 시에도 기존 rule 결과는 그대로 반환(핵심 기능 유지)
  - 사용자에게는 “법령 근거 조회 실패(원인 요약)”만 노출(키/민감정보는 노출 금지)

