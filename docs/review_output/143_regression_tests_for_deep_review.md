# 143. Regression Tests for Deep Review

## 목적
- “깨끗한 입력(visible text)” → “clause-aware 질문/법령/수정문안” → “깨지지 않는 docx 출력” 흐름이 다시 퇴행하지 않도록 회귀 테스트를 추가한다.

## 추가된 테스트(요구사항 매핑)
### 1) Track changes 있는 docx 입력 테스트
- [test_docx_extraction.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py)
- 검증:
  - `final` 정책에서 삭제문(`w:delText`)은 제외, 삽입문(`w:ins`)은 포함

### 2) XML 태그가 clause text에 남지 않는지 테스트
- [test_docx_extraction.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py)
- [test_docx_output_pipeline.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py)
- 검증:
  - 추출 결과에 WordprocessingML 마커가 남으면 extraction 단계에서 실패
  - docx writer 입력 텍스트에 마커가 있으면 생성 단계에서 실패

### 3) 질문이 clause-aware로 달라지는지 테스트
- [test_question_clause_aware.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_question_clause_aware.py)
- 검증:
  - 대리점/위탁(비용전가) 텍스트 vs 개인정보 텍스트에서 상위 질문이 달라짐

### 4) 관련 법령이 직접 관련성 높은 결과만 남는지 테스트
- [test_law_search_rerank.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_law_search_rerank.py)
- 검증:
  - “광고 안내/홍보” 같은 노이즈 타이틀을 제거하고, 컨텍스트에 맞는 법령을 우선 유지

### 5) rewrite가 generic fallback만 반복하지 않는지 테스트
- [test_rewrite_engine_clause_specific.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_rewrite_engine_clause_specific.py)
- 검증:
  - 템플릿 덮어쓰기 대신, 원문 문장 기반 패치가 발생하고 rewrite_reason가 비어있지 않음

### 6) 생성된 docx 본문에 `<w:...>` 같은 XML 문자열이 없는지 테스트
- [test_docx_output_pipeline.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py)
- 검증:
  - `word/document.xml`의 모든 `w:t` 텍스트 노드에 `<w:`/`w:rPr` 등이 포함되지 않음

## 실행 방법
- 전체 테스트 실행:
  - `python -m unittest`
- 선택 실행(핵심 회귀):
  - `python -m unittest runtime.tests.test_docx_extraction runtime.tests.test_docx_output_pipeline runtime.tests.test_question_clause_aware runtime.tests.test_law_search_rerank runtime.tests.test_rewrite_engine_clause_specific`

