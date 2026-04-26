# 141. Clause-specific Rewrite Engine Fix

## 문제
- 기존 `recommended_rewrite`가 규칙별 “템플릿 문장”을 그대로 반환해 조항 맥락과 무관하게 generic하게 보였다.
- `rewrite_reason`도 조항의 실제 문제 문구를 지칭하기보다는 룰/이슈 나열 수준이었고, AI가 실패하면 더더욱 동일 템플릿이 반복됐다.

## 목표(적용됨)
- 원문 clause를 기반으로 문제 표현만 최소 변경으로 수정한다.
- detected issue + related rule(+matched_keywords) + related law(있으면) 정보를 함께 사용한다.
- generic fallback_text를 그대로 복붙하지 않는다.
- OpenAI가 실패해도 deterministic fallback이 clause-specific한 수정문안/이유를 제공한다.

## 변경 사항(코드 흐름 기준)
### 1) Deterministic clause-specific rewrite 엔진 추가
- 파일: [rewrite_engine.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)
- 입력: `clause_text` + `applied_rules[]`(rule_id + matched_keywords)
- 출력: `suggested_rewrite` + `rewrite_reason` + `reason_codes`
- 정책:
  - 문장 단위로 split 후, “문제 키워드가 포함된 문장”만 패치한다.
  - 패치가 가능한 경우에만 rewrite를 생성(무조건 덮어쓰지 않음).
  - 현재 구현된 rule_id: `RISK-001/002/004/005/006`

### 2) revision 단계에서 템플릿 복붙 대신 rewrite_engine 사용
- 파일: [revision.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
- 변경:
  - `recommended_rewrite = replacement_texts[0]`(템플릿) → `propose_clause_specific_rewrite(...)` 결과로 교체
  - `rewrite_reason`를 revision item에 같이 저장
  - `fallback_text`는 “참고용 템플릿”으로만 남기고, 추천 문안에 직접 사용하지 않음

### 3) clause_level에서 rewrite_reason 우선 유지 + AI 프롬프트 강화
- 파일: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- 변경:
  - revision에서 내려온 `rewrite_reason`가 이미 있으면 “룰/이슈/법령 제목 나열”로 덮어쓰지 않도록 방지
  - AI 프롬프트에 다음 제약을 추가:
    - 원문 조항의 적절한 표현은 유지
    - 문제되는 표현만 최소 변경
    - fallback_rewrite를 그대로 복사/재진술 금지

## 검증(회귀 테스트)
- 파일: [test_rewrite_engine_clause_specific.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_rewrite_engine_clause_specific.py)
- 확인:
  - `RISK-001`(책임 상한) 케이스에서 “상한” 등 구체 표현이 포함된 rewrite가 생성되고, 원문과 다르게 변경됨
  - `RISK-002`(면책/배상) 케이스에서 원문 맥락(Supplier 등)을 유지한 채 절차/제한 문구가 붙음

