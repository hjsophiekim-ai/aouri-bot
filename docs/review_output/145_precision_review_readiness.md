# 145) Precision Review Readiness 최종 판정

평가 기준(요청):
1. 실제 첨부 계약서를 깨끗하게 읽는가
2. 질문이 계약 내용별로 달라지는가
3. clause별 검토가 되는가
4. 법령/판례 grounding이 직접적이고 타당한가
5. 수정문안이 정밀하고 clause-specific한가
6. 최종 Word 파일이 깨지지 않는가

---

## 현재 상태(코드/테스트 기준)

다음 항목들은 코드 수정 및 자동 테스트로 검증되었습니다.

- WordprocessingML(`<w:...>`, `w:rPr`, `w:delText` 등) 마커가 입력(추출/분석)에 유입되면 차단
  - [word_markers.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/word_markers.py)
  - 테스트: [test_docx_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py), [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py)
- clause extraction 리빌드(헤딩 기반 + fallback + 품질 리포트)
  - [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
- 질문 엔진이 “이미 명시됨”을 감지해 불필요 질문을 줄이고, missing controls 질문을 추가
  - [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
- clause-level grounding에서 노이즈(조례안/공고/광고 등)를 제거하고 scope를 분리
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
- rewrite 엔진이 패턴 미매칭에도 clause-specific rewrite를 생성
  - [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)
- 생성된 docx의 텍스트 노드에 `<w:...>` 문자열이 포함되지 않음(주입 방지)
  - 테스트: [test_docx_output_pipeline.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py)

---

## 아직 미검증(실제 파일 필요)

아래 항목은 “문제가 된 실제 계약서(DESKER MATE track changes docx)”가 작업 디렉터리에 없어, 실제 업로드 기반으로 재현/검증을 완료하지 못했습니다.

- 실제 첨부 계약서를 깨끗하게 읽는지(특히 Word track changes/복잡한 레이아웃)
- 실제 계약서 기준으로 질문이 달라지는지
- 실제 계약서 기준으로 clause별 검토가 충분히 분해되는지
- 실제 계약서 기준으로 grounding이 타당한지(법령 API 키/화이트리스트도 필요)
- 실제 계약서로 docx 생성이 “법무팀이 읽을 수 있는 수준”인지

---

## 최종 판정(현재 시점)

- 판정: **부분 도달**
  - 자동 테스트로 “깨짐 방지(Word XML 유입 차단, docx 출력 안전성)”와 “엔진 구조 개선(clause/question/grounding/rewrite)”는 검증됨
  - 다만, 요청한 실제 계약서 파일 기반의 end-to-end 재검증이 아직 수행되지 않아 “실사용 가능” 판단은 유보

