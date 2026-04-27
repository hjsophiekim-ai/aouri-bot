# 137) DOCX 추출 파이프라인 수정: WordprocessingML 유입 차단

목표:
- WordprocessingML 원문(document.xml) 태그가 review 입력으로 들어가지 않게 하기
- w:rPr, w:pPr, w:ins, w:del, w:delText 같은 XML 조각이 clause text에 남지 않게 하기
- track changes(삽입/삭제) 문서를 안전하게 처리할 정책 확정
- XML 태그가 clause text에 남아있으면 검증 단계에서 실패 처리
- 회귀 테스트 추가

---

## 1) 구현 요약

### 1.1 “visible text” 기준 추출

- 기존/현재 모두 `.docx`는 zip에서 WordprocessingML을 XML 파싱해 `w:t` 텍스트를 추출합니다.
- 구현: [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)
  - docx 파서: [extract_text_from_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L108-L140)
  - XML walk: [_extract_visible_text_from_word_xml](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L143-L196)

python-docx는 현재 환경에 설치되어 있지 않아(`python-docx False`), 표준 라이브러리 기반 “적절한 파서(ElementTree + WordprocessingML)”로 구현합니다.

### 1.2 raw XML 문자열을 review 입력으로 넘기지 않기

- 추출 결과는 `TextExtractionResult.text`(정규화된 plain text)만 session 저장 및 review 입력으로 사용합니다.
- raw XML은 `raw_markup_text`로 추출 단계에서만 보관 가능하나(기본은 저장하지 않음), review 입력으로는 절대 사용하지 않습니다.

### 1.3 Track Changes 처리 정책

정책: **기본값은 “최종 visible text 우선(final)”**
- `w:ins`(삽입)는 포함
- `w:del`/`w:delText`(삭제)는 제외
- 테스트로 검증: [test_docx_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py#L33-L57)

### 1.4 XML 마커 잔존 시 실패 처리(강화)

WordprocessingML 마커를 정규식 기반으로 탐지해(변형 포함) 다음 단계로 못 가게 막습니다.

- 공통 탐지: [word_markers.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/word_markers.py)
- 적용 지점:
  - docx 추출 결과 검증: [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L69-L96)
  - txt 입력도 검증(renamed XML/text 유입 차단): [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py#L59-L67)
  - review analyze 직접 입력 차단: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L614-L620)
  - clause-level 단계에서도 추가 block: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L46-L94)

---

## 2) “clean_text / raw_markup_text” 분리 저장 정책

현재 구현:
- clean_text: 항상 session 저장 및 review 입력에 사용
- raw_markup_text: 추출 모듈 내부에서만 생성(최대 20000자 제한)  
  - 운영에서는 기본 저장하지 않음(계약 본문이 그대로 들어갈 수 있어 용량/민감정보 이슈 가능)

필요 시(디버깅 전용) 다음 확장을 권장:
- 환경변수 플래그로 `raw_markup_text`를 별도 파일로 저장(세션ID 기반)  
- session에는 `has_track_changes`, `policy` 등 메타만 저장

---

## 3) 검증(회귀 테스트)

추가/기존 테스트:
- track changes 문서에서 “삭제문 제외/삽입문 포함”: [test_docx_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py#L33-L57)
- visible text에 `<w:rPr>` 같은 마커가 나오면 추출 실패: [test_docx_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py#L58-L73)
- txt로 유입되는 `w:rPr`도 차단: [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L14-L28)

