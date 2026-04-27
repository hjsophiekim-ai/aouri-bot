# 142) 최종 Word(DOCX) 출력 파이프라인 점검/수정

문제(관찰):
- 출력 Word에 raw XML 조각이 본문으로 들어가 깨지는 현상

현 상태 점검 결과:
- 현재 repo의 DOCX 생성은 “문서 객체(DOM) 기반 WordprocessingML 생성 + zip 패키징” 방식이며,
- 입력 텍스트에 `<w:...>`/`w:rPr` 등 WordprocessingML 마커가 포함되면 DOCX 생성을 거부하도록 되어 있습니다.

---

## 1) 구현 파일

- DOCX 생성기: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- 다운로드 엔드포인트: [server.py:/api/revision/download_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1089-L1223)

---

## 2) “raw XML을 본문에 쓰지 않기” 방어선

### 2.1 Word XML 마커 검증(입력 텍스트)

- 모든 텍스트(w:t)에 들어가기 전에 검증:
  - [docx_writer.py:_ensure_safe_text](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L44-L47)
- 탐지 로직은 여러 파일에 흩어져 있던 것을 정규식 기반으로 통합:
  - [word_markers.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/word_markers.py)

### 2.2 upstream(추출/분석 입력)에서의 차단

- `.docx` 추출 단계에서 마커가 나오면 추출 실패: [text_extract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)
- review analyze 입력에서도 차단: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L614-L620)
- clause-level 진입 시 마커 발견하면 분석 중단(block): [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L46-L94)

즉, “DOCX가 깨져 보이는” 원인을 대부분 upstream에서 제거하도록 강화했습니다.

---

## 3) MVP 출력 구성 충족 여부

현재 DOCX는 최소 MVP 구성으로 아래를 포함합니다.
- 원문 조항(변경 조항만) + redline(underline/strike)
- 수정문안(조항별 suggested_rewrite 기반)
- 수정 이유(rewrite_reason)
- 관련 법령(조항별 related_laws에서 title 추출)
- 강조 표시(색/밑줄/취소선)

구현:
- [build_revision_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L220-L460)

---

## 4) 회귀 테스트

- 생성된 docx의 `w:t` 텍스트 노드에 `<w:`/`w:rPr`/`w:delText` 문자열이 없어야 함:
  - [test_docx_output_pipeline.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py)

