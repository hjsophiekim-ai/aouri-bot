# 143) Deep review 회귀 테스트 추가

목표:
- 이번에 드러난 구조적 문제(Word XML 유입, clause 품질 붕괴, 질문 generic, grounding 노이즈, rewrite generic 반복, docx 출력 깨짐)를 다시 막기 위한 자동 테스트 추가

---

## 추가된 테스트 파일

- [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py)

---

## 요구사항 매핑

1) track changes 있는 docx 입력 테스트  
- 이미 존재: [test_docx_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_extraction.py#L33-L57)

2) XML 태그가 clause text에 남지 않는지 테스트  
- clause extractor가 WordprocessingML 마커를 감지하면 block 되는지 검사:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L20-L28)

3) 질문이 clause-aware로 달라지는지 테스트  
- 비용 조건이 충분히 명시된 계약 vs 부족한 계약에서 질문이 달라지는지 검사:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L30-L60)

4) 관련 법령이 직접 관련성 높은 결과만 남는지 테스트  
- 노이즈(조례안/채용 공고) 제거 및 관련 법령 유지 검사:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L62-L94)

5) rewrite가 generic fallback만 반복하지 않는지 테스트  
- 패턴 미매칭 문장에서도 최소 변경으로 rewrite가 생성되는지 검사:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L96-L104)

6) 생성된 docx 본문에 `<w:...>` 같은 XML 문자열이 없는지 테스트  
- 기존 테스트 유지:
  - [test_docx_output_pipeline.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py#L11-L39)

---

## 실행 방법

```bash
python -m unittest discover -s runtime/tests -p "test_*.py"
```

