# 질문 생성(/api/questions/generate) + 법령 검색 반영

목표:
- 계약서 내용에 따라 법률상 중요한 추가 질문이 자동으로 나오게 하기
- 기존 rule 기반 질문 생성은 유지

---

## 변경 내용

- `/api/questions/generate` 응답에 `law_search`를 포함했습니다.
- 또한 `law_search.queries`(예: “대리점법”, “하도급법”, “개인정보보호법”)를 질문 엔진 입력으로 전달해,
  - 해당 토픽에 매핑된 질문을 추가로 생성하도록 확장했습니다.

구현 위치:
- API: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- 질문 엔진: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)

---

## 추가된 질문 예시(토픽 기반)

- `대리점법` 토픽이 있으면:
  - `Q-LAW-001-dealer-consignment`: 위탁판매/위수탁 구조 여부
  - `Q-LAW-002-dealer-promo`: 판매장려금/판촉비/광고비/반품비 부담 여부
- `하도급법` 토픽이 있으면:
  - `Q-LAW-003-subcontract-tech`: 기술자료 요구/제공 조항 여부
  - `Q-LAW-004-subcontract-price`: 단가 조정/재작업 비용 부담 조항 여부
- `개인정보보호법` 토픽이 있으면:
  - `Q-LAW-005-privacy-transfer`: 개인정보 국외이전 가능성 여부

---

## 실패/비활성화 시

- `LAW_API_ENABLED=false` 또는 `LAW_API_KEY` 미설정이면
  - `law_search.enabled=false`로 내려오고,
  - 질문 엔진은 기존 rule 기반 질문만 생성합니다.

