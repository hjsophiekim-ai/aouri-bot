# 149) buyer_favorable rewrite 엔진 고도화(구매자/발주자 관점)

문제:
- 수정문안이 generic하고 상호주의 중심으로 평탄화되어 “구매자/발주자” 관점의 리스크 감소가 부족

원칙(요청 반영):
1) 원문이 이미 우리에게 유리하면 유지 또는 보강만  
2) 상대방에게 유리한 조항만 집중 수정  
3) 상호주의가 아니라 당사 리스크를 줄이는 방향  
4) 설치/시운전 계약 포인트(재위탁 승인, 안전책임, 검수/재검수, 지체, 보증, 책임제한/면책, 원상복구/추가비용 등) 엄격  
5) rewrite는 clause-specific(원문의 어느 부분을 어떻게 바꾸는지 명확)

---

## 1) posture 기반 rewrite 템플릿 분기

- `buyer_favorable`일 때:
  - 책임 상한은 “당사 책임 상한” 중심으로 제안(각 당사자 상호 캡 → 당사 보호 우선)
  - 면책/배상은 “상대방(공급자/시공자) 귀책 범위 내 당사 방어·면책” 구조로 제안
  - 비용 전가는 “사전 서면합의 + 항목별 상한/정산/증빙 + 상대방 귀책 비용 부담”을 명시

구현:
- [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

---

## 2) 설치/현장 작업 안전 포인트 보완(부재/약함 후보)

- buyer_favorable일 때만,
  - 안전 조항이 이미 충분히 유리한 경우는 수정하지 않음
  - 부족할 경우 최소한의 안전/재위탁 승인/통지/작업중지 구조를 추가

구현:
- [rewrite_engine.py:_rewrite_safety_gap](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

---

## 3) “우리에게 불리한지” 표시와 함께 동작

- rewrite가 생성되는 조항은 `unfavorable_to_us=true`로 함께 표시되도록 엔진에서 계산합니다.
- 구현:
  - [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

