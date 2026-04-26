# 국가법령정보 Open API 기능 분석 (가이드 근거)

본 문서는 국가법령정보 공동활용 OPEN API 가이드(목록/상세)에서 확인되는 정보만을 근거로, aouribot에 접목 가능한 기능 범위를 정리합니다.

출처:
- 가이드 목록: https://open.law.go.kr/LSO/openApi/guideList.do
- 가이드 상세: https://open.law.go.kr/LSO/openApi/guideResult.do (guideList에서 `openApiGuide('...')` 클릭 시 POST로 로딩)

---

## 1) 인증 방식

- 인증값은 요청 파라미터 `OC`로 전달됩니다. 가이드 표기: “신청한 API인증값”. (예: [현행법령(시행일) 목록 조회 API] guideResult)
- 실 호출 시 사용자 검증 실패 메시지로 **서버 장비의 IP주소 및 도메인주소 등록 필요**가 확인됩니다(잘못된 OC 예시 호출 기준).  
  - 예시 응답(JSON): `사용자 정보 검증에 실패하였습니다.`, `OPEN API 호출 시 사용자 검증을 위하여 정확한 서버장비의 IP주소 및 도메인주소를 등록해 주세요.`  
  - (출처: `https://www.law.go.kr/DRF/lawSearch.do?OC=test&target=law&type=JSON&query=...`)

## 2) 요청 방식

- 가이드에 안내되는 실제 데이터 API는 `www.law.go.kr/DRF/` 하위의 2종으로 구분됩니다.
  - **목록/검색형**: `http://www.law.go.kr/DRF/lawSearch.do?target=...`
  - **본문/상세형**: `http://www.law.go.kr/DRF/lawService.do?target=...`
  - (출처: 각 guideResult의 “요청 URL” 항목)

## 3) 응답 형식

- 요청 파라미터 `type`으로 출력 형태를 지정합니다.
  - 가이드 표기: `HTML/XML/JSON` (생략 시 기본값 XML) (출처: guideResult 요청변수 표)
- 따라서 aouribot 연동 시 기본은 `JSON`을 우선 사용하고, 필요 시 `XML`을 파싱하는 형태가 안전합니다.

## 4) 검색/상세조회(목록/본문) 방식

가이드 상의 “요청 URL” 기준으로, 일반적으로:
- `lawSearch.do`는 `query/page/display/sort` 계열 파라미터를 통해 목록을 조회합니다.
- `lawService.do`는 `ID` 또는 `MST` 등 식별자를 통해 본문을 조회합니다(예: 법령 본문 조회는 “ID 또는 MST 중 하나는 반드시 입력”이 안내됨).

예시:
- 법령 본문(현행법령(시행일) 본문 조회) 요청변수에는 `ID` 또는 `MST`(중 하나 필수), `efYd`(시행일, 필수) 등이 포함됩니다. (출처: `lsEfYdInfoGuide` guideResult)
- 판례 본문(판례 본문 조회) 요청변수에는 `ID(필수)`, `LM(선택)`이 포함됩니다. (출처: `precInfoGuide` guideResult)

---

## 5) 조회 가능한 데이터 종류(가이드에서 확인된 target 기준)

본 절은 `guideList/guideResult`를 기반으로, **aouribot 계약 검토에 직접 활용 가능한 범주** 중심으로 정리합니다.

### 5.1 법령정보

- 법령 목록 조회: `lawSearch.do?target=law` (예: `lsNwListGuide` “현행법령(공포일) 목록 조회 API”)  
- 법령 본문 조회: `lawService.do?target=law` (예: `lsNwInfoGuide` “현행법령(공포일) 본문 조회 API”)  
- 현행법령(시행일) 목록/본문: `target=eflaw` (예: `lsEfYdListGuide`, `lsEfYdInfoGuide`)
- 영문법령: `target=elaw` (예: `elaw` 그룹)

### 5.2 판례정보

- 판례 목록/본문: `target=prec`  
  - 목록: `precListGuide` → `lawSearch.do?target=prec`  
  - 본문: `precInfoGuide` → `lawService.do?target=prec`
- 행정심판례: `target=decc` (목록/본문)
- 헌재결정례: `target=detc` (목록/본문)

### 5.3 행정규칙

- 행정규칙 목록/본문: `target=admrul`
- 행정규칙 신구법비교: `target=admrulOldAndNew` (목록/본문)

### 5.4 자치법규

- 자치법규 목록/본문: `target=ordin`
- 법령-자치법규 연계현황/연계목록: `target=drlaw`, `target=lnkLs`, `target=lnkOrd` (가이드 제목 기준)

### 5.5 해석례

- 법령해석례 목록/본문: `target=expc`
- 부처별 법령해석: `target=*CgmExpc` 패밀리(예: `moelCgmExpc`, `molitCgmExpc`, `ntsCgmExpc` 등) (가이드 제목 기준)

### 5.6 기타(법률 검토에 활용 가능한 데이터)

가이드 목록에서 다음과 같은 “결정문/의견서/심사결정” 류 target들이 확인됩니다(일부 예시):
- 공정거래위원회 결정문: `target=ftc` (목록/본문)  
- 금융위원회 결정문: `target=fsc` (목록/본문)  
- 국민권익위원회 결정문: `target=acr` (목록/본문)
- 감사원 사전컨설팅 의견서: `target=baiPvcs` (목록/본문)
- 중앙환경분쟁조정위원회 결정문: `target=ecc` (목록/본문)

(출처: guideResult의 “요청 URL” 및 guideList/guideResult 제목)

---

## 6) 호출 제한/주의사항

- 가이드 상세 화면(guideResult) 전체 195건을 텍스트 검색(“쿼터/일일/분당/제한”) 기준으로 확인했을 때, **호출량 제한(쿼터) 수치가 직접 표기된 항목은 확인되지 않았습니다.** (출처: guideResult HTML 일괄 검색)
- 다만, DRF 실제 호출 실패 메시지에서 **서버 IP/도메인 등록 필요**가 확인되므로, 운영 환경에서:
  - 키 발급 + IP/도메인 등록(화이트리스트) 절차가 필수 전제입니다. (출처: DRF 호출 실패 메시지)

---

## 7) 법령 최신성 확인 방식

가이드 상세의 변경이력(페이지 상단의 날짜/이슈번호 라인)을 통해, 가이드가 지속적으로 “현행화”되고 있음을 확인할 수 있습니다.  
예: `lsEfYdListGuide` 변경이력에 “OPEN API 가이드페이지 현행화” 문구가 포함됩니다. (출처: `lsEfYdListGuide` guideResult 변경이력)

단, “데이터 최신성(법령 개정 반영 시점) 자체를 확인하는 전용 파라미터/엔드포인트”는 본 문서 작성 범위에서 가이드로 확인되지 않았습니다(추정 금지).

---

## 8) aouribot에 붙이기 적합한 API 우선순위(근거 기반)

### 8.1 1순위 (즉시 활용)

- **법령 목록/본문 (`target=law`, `target=eflaw`)**
  - 계약서 조항 검토에서 가장 빈번히 인용되는 1차 근거
  - `lawSearch`→`lawService`로 “검색→본문” 플로우가 명확
- **판례 목록/본문 (`target=prec`)**
  - 조항 해석/리스크 설명 강화에 직접 효과
- **법령해석례 (`target=expc`, 부처별 `*CgmExpc`)**
  - 규제/실무 해석 근거로 활용 가능

### 8.2 2순위 (추가 가치)

- **행정규칙 (`target=admrul`, `target=admrulOldAndNew`)**
  - 컴플라이언스/내부통제 문구 근거 보강
- **행정심판례/헌재결정례 (`target=decc`, `target=detc`)**
  - 특정 리스크(행정제재, 위헌성 등)에서 근거 강화

### 8.3 3순위 (상황별)

- **자치법규/연계 (`target=ordin`, `target=lnkLs`, `target=lnkOrd`, `target=drlaw`)**
  - 설치/현장/지자체 규제 이슈가 있을 때 효과적
- **위원회/기관 결정문/의견서(예: `ftc`, `fsc`, `acr`, `baiPvcs` 등)**
  - 특정 도메인(공정거래/금융/권익위 등)에서 근거 다양화

