# 152. Buyer-favorable Regression Tests (LG 장비공급/설치)

## 목적
- “장비공급/설치/시운전” 계열 계약에서 검토 방향(buyer_favorable)과 산출물(redline/docx/매핑/무관 법령)을 회귀 테스트로 고정한다.

## 추가된 테스트
- 파일: [test_buyer_favorable_regression.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression.py)
- LG 샘플 계약 fixture:
  - [lg_purchase_installation.txt](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/fixtures/lg_purchase_installation.txt)

## 요구사항 매핑(필수 1~7)
1) LG 장비공급/설치 계약 테스트
- fixture 기반으로 `build_clause_level_result()` 실행

2) buyer_favorable posture 활성화 테스트
- `bundle.meta["review_posture"] == "buyer_favorable"` 검증

3) 이미 우리에게 유리한 안전조항을 불필요하게 수정하지 않는지
- “안전관리” 조항에 `suggested_rewrite`가 생성되지 않는지 확인

4) 일방 면책/책임제한은 구매자에게 유리하게 수정하는지
- “손해배상/면책” 조항에 대해 `suggested_rewrite`가 생성되고,
  - 책임 상한/제한 또는 제3자 청구 절차(통지/방어권 등) 같은 보호 문구가 포함되는지 확인

5) 대리점법 같은 무관 법령이 붙지 않는지
- `_derive_topics(entity='퍼시스', contract_type='장비공급/설치/시운전', ...)`에서 `대리점법`이 포함되지 않는지 검증
- 참고: 퍼시스 기본 우선 토픽에 `대리점법`이 포함되어 있던 문제를 컨텍스트 기반 필터로 제거함
  - [priority_rules.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/law/priority_rules.py)

6) redline docx에서 전체 문장이 아니라 변경 부분만 빨간색인지
- 생성된 docx의 `word/document.xml`을 파싱해서
  - 빨간색 run과 일반 run이 함께 존재하는지(=전체가 빨간색이 아님) 검증

7) clause title mismatch가 발생하면 실패하는지
- `build_revision_docx()`가 `ValueError`로 실패하는지 검증

