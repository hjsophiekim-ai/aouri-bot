# 137. DOCX Clean Extraction Fix (WordprocessingML 혼입 방지)

## 목표
- DOCX에서 WordprocessingML(document.xml) 마크업이 review 입력으로 들어가지 않게 한다.
- `w:rPr`, `w:pPr`, `w:ins`, `w:del`, `w:delText` 같은 XML 조각이 clause text에 섞이면 검증 단계에서 실패 처리한다.
- Track Changes(삽입/삭제)가 있는 문서도 “현재 보이는 텍스트(final)” 기준으로 안전하게 추출한다.
- 필요 시 clean text와 raw markup text를 분리 보관할 수 있게(디버깅용) 분리 반환한다.

## 문제 원인(코드 흐름)
- DOCX는 zip 내부의 `word/document.xml`(및 header/footer 등)로 구성된 WordprocessingML이다.
- 추출 단계에서 “문자열 기반 정규식”으로 `<w:t>`를 긁는 방식은 다음을 유발할 수 있다.
  - Track Changes 영역(`w:ins`, `w:del`)의 처리 정책이 없어서 삭제문/삽입문이 섞인다.
  - 파싱 실패 시 fallback로 XML 조각을 텍스트로 취급하는 경로가 생기면 `<w:...>` 조각이 결과 텍스트로 유입될 수 있다.
- 이 텍스트가 업로드→세션 저장→review analyze→clause extraction→docx 출력까지 그대로 흘러가며, 조항/결과/최종 docx 본문에 “XML 조각”이 보이는 형태로 깨진다.

## 수정 내용
### 1) DOCX 텍스트 추출을 “visible text” 파싱으로 고정
- 파일: [text_extract.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)
- DOCX zip에서 대상 파트:
  - `word/document.xml`
  - `word/headerN.xml`, `word/footerN.xml`
  - `word/footnotes.xml`, `word/endnotes.xml`
- XML 파서는 `xml.etree.ElementTree`로 구조를 파싱하고, 문단(`w:p`) 기준으로 텍스트 노드만 수집한다.
  - 텍스트 노드: `w:t`, `w:delText`
  - 레이아웃 요소 일부: `w:tab`(공백), `w:br`/`w:cr`(개행), `w:noBreakHyphen`(하이픈)
- “정규식 `<w:t>` fallback” 경로를 제거하고, WordprocessingML XML이 깨져 있으면 실패 처리한다.

### 2) Track Changes 처리 정책(삭제/삽입)
- 기본값(현재 적용): `final`
  - 삭제(`w:del`) 내부 텍스트는 제외
  - 삽입(`w:ins`) 내부 텍스트는 포함
- 지원 정책: `original`
  - 삽입(`w:ins`) 내부 텍스트는 제외
  - 삭제(`w:del`) 내부 텍스트(`w:delText` 포함)는 포함
- 현재 구현은 `meta.track_changes_policy`로 정책을 반환한다(추후 설정값/옵션화 가능).

### 3) Raw XML 문자열을 review 입력으로 넘기지 않기
- 추출 함수는 `text`(clean)와 `raw_markup_text`(디버깅용)를 분리 반환한다.
- 세션 생성 및 review/analyze 입력에는 `text`만 사용한다.

### 4) WordprocessingML 마커 검증(실패 처리)
- 추출된 최종 텍스트에 다음 마커가 포함되면 실패 처리한다.
  - `<w:`, `</w:`, `<?xml`, `xmlns:w=`
  - `w:rPr`, `w:pPr`, `w:ins`, `w:del`, `w:delText`
- 목적: “원문이 아니라 XML 문자열이 들어갔다”는 케이스를 조기 차단해서 downstream(clause/review/docx)에서 깨지지 않게 한다.

## 회귀 테스트
- 파일: [test_docx_extraction.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py)
- 커버하는 케이스
  - Track Changes가 있는 WordprocessingML에서 `final` 정책이 삭제문을 제거하고 삽입문/현재문을 유지
  - “보이는 텍스트” 자체에 `<w:rPr>` 같은 마커가 들어오면 추출 단계에서 실패
  - WordprocessingML XML 자체가 깨진 경우 추출 단계에서 실패

## 영향 범위
- 업로드(`/api/upload`)로 들어오는 DOCX는 세션 저장 전에 clean text로 정규화되고, WordprocessingML 마커가 남으면 실패 처리된다.
- 이로 인해 review 결과, clause text, 최종 docx 생성까지 “XML 조각이 본문으로 노출되는 문제”의 1차 원인이 제거된다.

