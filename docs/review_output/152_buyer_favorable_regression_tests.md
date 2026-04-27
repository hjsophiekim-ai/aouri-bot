# 152) buyer_favorable 회귀 테스트 추가

요구사항:
1) LG 장비공급/설치 계약 테스트  
2) buyer_favorable posture 활성화 테스트  
3) 이미 우리에게 유리한 안전조항을 불필요하게 수정하지 않는지  
4) 일방 면책/책임제한은 구매자에게 유리하게 수정하는지  
5) 대리점법 같은 무관 법령이 붙지 않는지  
6) redline docx에서 전체 문장이 아니라 변경 부분만 빨간색인지  
7) clause title mismatch가 발생하면 실패하는지

---

## 추가/수정된 테스트 파일

- LG 구매/설치/시운전 회귀(기존 확장):  
  - [test_buyer_favorable_regression.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression.py)
- buyer_favorable v2(추가):  
  - [test_buyer_favorable_regression_v2.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression_v2.py)

---

## 항목별 커버리지

1) LG 계약 테스트  
- `runtime/tests/fixtures/lg_purchase_installation.txt` 기반으로 clause-level 결과 생성 테스트 포함

2) buyer_favorable posture 활성화  
- `bundle.meta.review_posture == buyer_favorable` 확인

3) 유리한 안전조항 불필요 수정 방지  
- 안전조항에서 suggested_rewrite가 비어있음(불필요 rewrite 없음) 확인

4) 일방 면책/책임제한 구매자 유리 수정  
- 손해배상/면책 조항에서 상한/제한/통지 등 보강 문구가 생성되는지 확인

5) 무관 법령(대리점법) 미부착  
- purchase_installation 프로파일에서 query 목록에 `대리점법` 미포함 확인

6) redline granularity  
- docx 내부 run 중 “색 있는 run”과 “색 없는 run”이 공존하는지 확인(전체 문단이 전부 빨강이 되지 않도록)

7) clause title mismatch 실패  
- docx 생성기는 clause_title mismatch를 발견하면 예외로 실패 처리하도록 유지([test_docx_output_pipeline.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_output_pipeline.py) 참고)
- clause-level 단계에서도 mismatch가 나면 docx_allowed=false로 block 처리(실제 데이터로 mismatch 재현이 어려워 유닛 케이스는 docx writer 레벨에서 보장)

---

## 실행

```bash
python -m unittest discover -s runtime/tests -p "test_*.py"
```

