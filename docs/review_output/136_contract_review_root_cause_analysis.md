# 136) 계약 검토 품질 저하 Root Cause 분석 (엔진 관점)

본 문서는 UI 문제가 아니라 “엔진/파이프라인” 관점에서 아래 증상 4가지를 코드 흐름 기준으로 추적한 결과입니다.

- 증상 1) 계약별로 질문이 달라지지 않고 generic
- 증상 2) 검토 결과 원문 조항에 Word XML 태그(w:rPr, w:delText, w:ins 등)가 섞여 깨져 보임
- 증상 3) 관련 법령/판례가 조항과 직접 관련 없는 것도 섞여 grounding 품질 낮음
- 증상 4) 최종 Word 파일도 XML 조각이 본문으로 들어가 깨짐

---

## 1) 업로드된 docx/pdf/hwp가 어떤 파이프라인으로 텍스트화되는지

### 1.1 업로드 엔드포인트

- 업로드 처리: [server.py:_handle_upload](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1623-L1730)
  - multipart → 임시 파일 저장 → [extract_text_from_file](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L56-L106) 호출
  - 추출 성공 시 `create_session(..., text=extraction.text)`로 “분석용 텍스트”를 세션 JSON에 저장

### 1.2 확장자별 텍스트 추출

- 텍스트 추출 진입점: [text_extract.py:extract_text_from_file](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L56-L106)
  - `.docx`: zip + WordprocessingML 파싱(visible text 기반)
    - [extract_text_from_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L108-L140)
    - [ _extract_visible_text_from_word_xml](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L143-L196)
  - `.pdf`: MVP에서 추출 제외(실패 반환)
  - `.hwp/.hwpx`: 현재 미지원(확장자 불일치로 실패)
  - `.txt`: 단순 read + 정규화

### 1.3 Word XML(WordprocessingML) 마커 방어선

현재 시스템은 “Word XML 조각이 분석 입력으로 들어가는 것”을 강하게 차단하도록 되어 있습니다.

- 업로드(docx/txt) 추출 단계에서 차단:
  - [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L56-L96)
  - `WordprocessingML markers detected ...` → `success=false`
- 텍스트 직접 입력(review analyze)에서도 차단:
  - [server.py /api/review/analyze](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L608-L620)
- clause-level 처리에서도 차단(추가 방어):
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L46-L94)

즉, **정상 경로(업로드 docx/텍스트 입력)라면 `<w:...>` 계열 문자열이 review 입력으로 들어가는 것은 원칙적으로 “막혀야” 합니다.**

---

## 2) 실제 review analyze에 들어가는 입력이 무엇인지

### 2.1 /api/review/analyze 직접 호출 경로

- 입력 텍스트: request body의 `text`
- 처리: [server.py /api/review/analyze](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L596-L666)
  - `build_clause_level_result(... text=str(text) ...)`로 진입

### 2.2 업로드 기반(question session) 경로

- 업로드 시 session에 저장된 `text`가 review 입력이 됨
  - [storage.py:create_session](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L61-L120)
  - [storage.py:run_review_with_session](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L131-L159)

---

## 3) clause extraction 전에 어떤 cleaning/normalization을 거치는지

### 3.1 전처리(추출 단계)

- `.docx/.txt` 모두 공통으로:
  - 제로폭/컨트롤 문자 제거
  - 공백/개행 정규화
  - WordprocessingML 마커 감지 시 실패 처리
- 구현: [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)

### 3.2 조항 추출(Clause Extraction)

- clause-level에서 조항 추출 수행:
  - [clause_level.py:build_clause_level_result](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L46-L94)
- 조항 파서(개편됨):
  - [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
  - 한글 `제1조`, 영문 `Article 1` 헤딩 기반 분리
  - 너무 긴 조항은 하위 번호 패턴으로 sub-split
  - XML/태그로 보이는 라인/조각은 drop 또는 제거
  - 결과 리포트를 meta에 포함

---

## 4) 질문 생성기가 어떤 입력을 기준으로 질문을 고르는지

질문 생성은 단순 “법인/계약유형 고정 질문”이 아니라, 다음 정보를 함께 씁니다.

- 입력:
  - 계약 텍스트(전체)
  - rule 매칭 결과(detected_rule_ids)
  - clause-level 결과(clause_results에 포함된 related_rules)
- 구현:
  - API: [server.py:_handle_questions_generate](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1224-L1318)
  - 엔진: [generator.py:generate_questions](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L44-L120)

따라서 질문이 generic하게 보인다면, 원인 후보는:
- (A) clause extraction이 제대로 안 되어 `clause_results`가 빈약/왜곡됨
- (B) 계약 텍스트에 핵심 키워드가 깨져(예: XML 조각, 줄바꿈/문단 구조 붕괴) 키워드 기반 판단이 실패
- (C) 질문 엔진이 “이미 계약서에 명확히 있는 내용”을 감지하지 못해 불필요 질문을 계속 생성

이번 수정에서는 (C)를 개선하기 위해 “명시된 비용 조건(상한/정산/증빙/서면합의)이 있으면 질문을 생략”하는 로직을 추가했습니다.

---

## 5) law_search가 어떤 키워드/토픽으로 검색하는지

### 5.1 clause-level grounding 흐름

- 조항별 related_laws 생성:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L152-L168)
  - 각 조항의 `original_text` + `related_rules`를 넣어 검색

### 5.2 검색 토픽/쿼리 생성 및 노이즈 문제(원인)

- 검색 토픽 생성:
  - [search_service.py:_derive_topics](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L144-L185)
- 기존(문제 원인): clause-level 검색에도 법인 우선순위 토픽이 섞이면,
  - 조항 자체와 상관없는 토픽(예: 제조물/광고/조례 등)이 쿼리에 포함될 수 있어
  - 결과에 노이즈가 섞이고 grounding 신뢰도가 떨어짐

### 5.3 개선(이번 수정)

- `scope` 개념 도입:
  - `scope="contract"`: 계약 전체 근거(상대적으로 넓게)
  - `scope="clause"`: 조항 근거(좁게)
- clause scope에서는:
  - 법인 우선순위 토픽을 기본적으로 prepend 하지 않음
  - 판례는 기본적으로 비활성(필요 시 별도 룰/템플릿을 추가해 직접 연결될 때만 사용)
- 구현:
  - [search_service.py:search_for_review(scope=...)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L35-L66)

---

## 6) docx 최종 출력이 원문 텍스트가 아니라 XML 문자열을 받고 있는지

DOCX 생성은 현재 “raw XML 문자열을 본문에 붙이는 방식”이 아니라, WordprocessingML DOM을 구성해 zip(docx)로 패키징합니다.

- 구현: [docx_writer.py:build_revision_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L220-L460)
- 보호:
  - 입력 텍스트에 WordprocessingML 마커가 있으면 생성 자체를 거부합니다.
  - [docx_writer.py:_ensure_safe_text](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L44-L47)

따라서 “Word 파일에 `<w:...>`가 본문으로 들어가 보인다”면, 가능한 원인은:
- (A) docx 생성기가 아니라 “다른 경로(예: 텍스트 파일 다운로드/미리보기)”를 Word로 열어 발생
- (B) 입력 텍스트에 WordprocessingML 마커가 포함되는데도 방어선이 누락된 경로가 존재(세션 기반/특정 엔드포인트)
- (C) Word XML 마커가 `<w:...>` 형태가 아닌 변형 형태로 들어와 탐지에서 누락(이번 수정에서 정규식 기반 탐지로 강화)

---

## 증상별 Root Cause 정리

### 증상 1) 질문이 generic

- 깨지는 레이어:
  - **clause extraction 품질** 또는 **질문 엔진의 “이미 명시됨 감지” 부족**
- 코드 근거:
  - 질문 엔진은 `contract_text` + `clause_results`를 사용함: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L44-L120)
  - clause_results는 조항 분해 + rule 매핑이 선행되어야 함: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L73-L151)
- 1차 개선:
  - 조항 파서 재구성 + “명시된 비용 조건이 있으면 질문 생략” 로직 추가

### 증상 2) 조항 텍스트에 Word XML 태그 섞임

- 깨지는 레이어:
  - **텍스트 추출 단계 또는 세션 저장 단계에서의 방어선 누락/우회**가 있을 때 발생
- 방어선:
  - docx 추출/텍스트 입력/조항 추출 모두 WordprocessingML 마커 탐지 시 block 처리
  - 구현 공통화: [word_markers.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/word_markers.py)
- 1차 개선:
  - 마커 탐지를 정규식 기반으로 강화(`w14:` 등 변형 포함)
  - clause-level 진입 시 마커 발견하면 분석을 즉시 중단(block)

### 증상 3) 관련 법령/판례 grounding 품질 낮음

- 깨지는 레이어:
  - **law_search 토픽/쿼리 생성 로직**(너무 넓음) + **rerank/필터 약함**
- 원인:
  - clause 단위에도 법인 우선순위 토픽이 섞이면 노이즈가 증가
- 1차 개선:
  - `scope="clause"`에서 쿼리 폭을 줄이고 판례는 기본 비활성
  - 텍스트/키워드/룰 기반 overlap 점수로 rerank 및 노이즈 제목 제거

### 증상 4) 최종 Word 파일에 XML 조각이 본문으로 들어감

- 깨지는 레이어:
  - DOCX 생성기는 입력에 마커가 있으면 거부하도록 되어 있으므로,
  - 실제로는 “분석 입력이 깨진 상태(= 마커 포함)”가 더 upstream에서 발생했고,
  - 그 결과물이 다른 경로로 Word에 들어가거나, 탐지 누락이 있었을 가능성이 큼
- 1차 개선:
  - WordprocessingML 마커 탐지 강화 + clause-level 단계에서 block
  - 생성 파이프라인의 입력(원문/수정문/사유/법령 제목)에 대한 마커 검증 유지/강화

---

## 우선순위(무엇을 먼저 고쳐야 하는지)

1) **DOCX/텍스트 입력에서 WordprocessingML 마커가 리뷰 입력으로 유입되는 것 차단(최우선)**
   - 방어선 공통화 + clause-level block 강화
2) **조항 추출 파서 품질 개선(다음 우선)**
   - 조항 단위가 안정적이어야 질문/grounding/rewrite가 모두 개선됨
3) **clause-aware law_search 폭 축소 + rerank/필터 강화**
4) **rewrite 엔진의 clause-specific 보장(패턴 미매칭 시에도 최소 변경 제안)**
5) **DOCX 출력은 “입력 검증 + 표/섹션 구성” 유지(현 구조는 방향성 유지하되, 입력이 깨지지 않게 upstream을 더 단단히)**

