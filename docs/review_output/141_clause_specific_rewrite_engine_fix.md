# 141) clause-specific rewrite 엔진 개선

문제:
- 추천 수정문안이 generic fallback_text를 그대로 반복하는 경우가 있어 “조항 맞춤형”으로 보이지 않음

목표:
- 원문 clause + detected issue + 관련 rule(+관련 law가 있으면)을 근거로
- 최소 변경(minimal change)으로 조항 맞춤형 수정문안을 생성
- OpenAI가 실패해도 deterministic rewrite가 clause-specific하도록 보장

---

## 1) 기존 구조

- 조항별 수정 제안은 다음 순서로 생성됩니다.
  1) 조항 추출
  2) rule 매칭 결과에서 조항별로 키워드 매칭
  3) rule_id별 rewrite_engine으로 “권장 문안(recommended_rewrite)” 시도
  4) 실패하면 rule_id별 generic fallback_text 사용

코드:
- [revision.py:suggest_revisions](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py#L202-L306)
- [rewrite_engine.py:propose_clause_specific_rewrite](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py#L223-L262)

---

## 2) 개선 내용(이번 수정)

### 2.1 “패턴 미매칭이면 None 반환” → “최소 변경 보완 문구 추가”

이전에는 target pattern을 못 찾으면 `None`을 반환해 fallback_text로 떨어졌습니다.
이제는 해당 rule이 적용된 이상, 패턴이 약해도 최소한의 보완 문구를 덧붙이는 방식으로 **항상 clause-specific rewrite를 생성**합니다.

예:
- RISK-001(책임 상한): 패턴이 없더라도 “책임 상한/간접손해 제외” 문구를 조항 말미에 추가
- RISK-006(비용 전가): “사전 서면합의 + 항목별 상한/정산/증빙 + 일방전가 금지”를 조항 말미에 추가

구현:
- [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

---

## 3) 회귀 테스트

- 패턴이 약한 문장에도 RISK-001 적용 시 “상한”이 포함된 rewrite가 생성되는지 확인:
  - [test_deep_review_regressions.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_deep_review_regressions.py#L96-L104)

