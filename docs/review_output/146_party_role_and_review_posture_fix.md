# 146) party_role 인식 + review_posture 도입/강화

요구사항:
1) party_role 인식 강화(구매자/공급자/발주자/설치·시운전 수요자)  
2) 상대방이 LG 같은 대기업 표준계약 제공자일 경우 supplier-friendly 조항을 더 엄격 탐지  
3) review/rewrite 엔진에 review_posture(buyer_favorable/seller_favorable/neutral) 개념 추가  
4) 기본값은 당사 보호 중심(특히 물품구매/설치/시운전은 buyer_favorable default)  
5) risk 탐지 외에 “우리에게 불리한지” 별도 표시

---

## 1) 구현 개요

### 1.1 party_role 추론 모듈 추가

- 파일: [party_role.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/party_role.py)
- 입력:
  - `contract_type`, `contract text`, `answers(질문 답변)`
- 출력:
  - `our_role` / `counterparty_role`
  - `our_label` / `counterparty_label`(갑/을 정의가 있으면 추출)
  - `counterparty_is_large_standard_provider`(LG 마커 기반)
  - `signals`(판별 근거 키워드)

### 1.2 review_posture 결정 로직 강화

- `infer_review_posture(...)`:
  - 우리 역할이 buyer/ordering_party면 `buyer_favorable`
  - 구매+설치/시운전 계약으로 보이면 기본 `buyer_favorable`
  - 그 외 `neutral`

적용 지점:
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - `party = infer_party_role(...)`
  - `review_posture = infer_review_posture(...)`
  - 결과 meta에 `party_role`, `review_posture` 포함

---

## 2) “우리에게 불리한지(unfavorable_to_us)” 표시 추가

- rule 기반 위험 탐지(High/Approval)와 별개로,
  - posture 관점에서 “당사 보호가 필요한 조항”을 표시합니다.
- 구현:
  - [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
  - `suggest_revisions(... posture, party)`가 `unfavorable_to_us`를 계산해 `items[*].unfavorable_to_us`로 반환
  - clause_level 결과에도 `clause_results[*].unfavorable_to_us`로 포함

---

## 3) 기본값 “당사 보호 중심” 반영

- 구매/장비공급/설치/시운전 계약은 기본 buyer_favorable로 유도
- buyer_favorable일 때 rewrite 템플릿이 “상호주의”가 아니라 “당사 리스크 감소” 방향으로 문구를 더 강하게 제안하도록 수정
  - [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

