# 142. DOCX Output Pipeline Fix (XML 조각 혼입 방지 + 객체 기반 생성)

## 문제
- 최종 DOCX 산출물 본문에 `<w:...>` 같은 XML 조각이 “텍스트로” 들어가 깨지는 증상이 있었다.
- clean copy에서도 동일 증상이 발생할 수 있었고, redline 강조도 입력 텍스트가 오염되면 그대로 노출됐다.

## 목표(적용됨)
- 최종 수정본 docx를 사람이 바로 열어서 읽을 수 있는 수준으로 생성한다.
- 입력 텍스트를 raw XML로 직접 이어붙이지 않고, “문서 객체(트리)” 기반으로 조립해 직렬화한다.
- 최소 MVP 구성(유지):
  1) 원문 조항
  2) 수정문안
  3) 수정 이유
  4) 관련 법령(현재는 clause_level에서 attach된 제목이 rewrite_reason에 포함될 수 있음)
  5) 강조 표시

## 변경 사항
### 1) DOCX 생성기를 ElementTree 기반으로 전면 교체
- 파일: [docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- 변경 전: 문자열 조립 + 수동 escape
- 변경 후: `xml.etree.ElementTree`로 `w:document/w:body/w:p/w:r/w:t`, `w:tbl` 등을 “노드”로 생성 후 `ET.tostring(..., xml_declaration=True)`로 직렬화
- 효과:
  - 텍스트가 `<`, `&` 등을 포함해도 자동 escape되어 “마크업 주입”이 구조적으로 차단됨
  - 생성 로직이 입력 문자열에 의존해 XML 구조를 만들지 않음

### 2) 입력 텍스트에 WordprocessingML 마커가 있으면 생성 실패
- docx writer 내부에서 `"<w:"`, `"w:rPr"` 등 마커가 입력 텍스트에 포함되면 `ValueError`로 실패 처리
- 목적: 상위 레이어에서 누락된 경우라도, 최종 산출물에 “XML 조각 텍스트”가 섞이는 것을 마지막 단계에서 차단

### 3) End-to-end 파이프라인 검증
- 서버 실행 후 스크립트로 업로드→조항별 결과→docx 다운로드를 재검증
  - 스크립트: [validate_docx_pipeline.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/scripts/validate_docx_pipeline.py)
  - 확인: docx 바이너리(zip) magic, 바이트 크기, `docx_allowed` 등

## 회귀 테스트
- 파일: [test_docx_output_pipeline.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py)
- 확인:
  - 생성된 `word/document.xml`의 모든 `w:t` 텍스트 노드에 `<w:`/`w:rPr` 같은 문자열이 포함되지 않음
  - 입력 텍스트에 WordprocessingML 마커가 있으면 생성이 실패함

