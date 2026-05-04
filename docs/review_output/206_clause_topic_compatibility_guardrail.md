# 206) clause topic classifier + rewrite topic compatibility guardrail

## 목표

- 조항 주제와 무관한 수정문안이 절대 삽입되지 않도록 한다.
  - 분쟁해결 조항에 판촉비/광고비/반품비/비용전가 문구 금지
  - 개인정보 조항에 설치/현장/산안법/작업중지권 문구 금지
  - 대리점 계약에 SOW/SBOM/오픈소스 문구 유입 금지(정황 없으면)

## 구현

### 1) 조항 주제 분류기

- title/text 기반으로 다음 토픽 중 하나로 분류한다.
  - `dispute`, `payment_settlement`, `personal_data`, `safety`, `open_source`, `sow_change`, `termination`, `cost_burden`, `dealer_unfair`, `other`
- 위치: [clause_topic.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_topic.py)

### 2) rule 매칭 단계에서 1차 차단(오탐 감소)

- 대리점 비용전가(RISK-006/ACT-009)는 비용/정산/대리점 토픽에서만 적용
- 안전(RISK-003/ACT-010)은 안전 토픽에서만 적용
- 정산(C-001)은 정산/비용 토픽에서만 적용
- 위치: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py#L83-L120)

### 3) rewrite 생성 이후 2차 차단(guardrail)

- 생성된 rewrite 텍스트 및 reason_codes 기반으로 rewrite 토픽을 추정하고,
  - 조항 토픽과 호환되지 않으면 suggested_rewrite를 제거한다.
- AI가 생성한 문구에도 동일한 guardrail이 적용된다.
- 위치: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py#L132-L166), [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L762-L821)

### 4) 하드 금칙어(현장/해외 정황 없으면 차단)

- 개인정보 토픽에서 `산업안전/중대재해/작업중지` 등은 무조건 차단
- 개인정보 토픽에서 `현장/시공/설치/공사`는 계약서 본문에 실제 정황이 있을 때만 허용
- 대리점 계약에서 강한 app_dev 정황이 없으면 `SOW/SBOM/오픈소스/소스코드` 유입 차단
- 위치: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L762-L815)

