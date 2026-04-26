# 법인별 법률 검색 우선순위 룰 (aouribot)

목표:
- 계약서 검토 시 “어떤 법률 검색을 우선할지”를 법인 기준으로 정렬
- 검색 토픽을 먼저 깔고, 이후 계약유형/키워드/rule 탐지에 따라 추가 토픽을 덧붙이는 방식

---

## 룰 코드

- 파일: [priority_rules.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/priority_rules.py)

정의된 법인별 우선순위(요청사항 반영):
- 퍼시스: 대리점법, 하도급법, 공정거래, 중대재해/산안
- 시디즈: 대리점법, 하도급법, 공정거래, 중대재해/산안, 제조물/품질
- 일룸: 대리점법, 표시광고/소비자보호, 모델계약, 하도급법, 중대재해
- 바로스: 특수관계인 거래, 물류/설치, 중대재해/산안, 하도급
- Fursys Vietnam: 생산이관, 기술자료, 하도급/공정거래, 현지 생산 리스크
- Sidiz America / Fursys America / Iloom Taiwan: 현지 판매/딜러/소비자보호/보증/광고

---

## 적용 지점

- 검색 토픽 도출 함수에서 가장 먼저 법인 우선순위 토픽을 prepend 합니다.
- 파일: [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

---

## 운영 원칙(권장)

- 법인 우선순위는 “검색 순서/가중치”일 뿐이며, 실제 위험 판정은 기존 rule 기반으로 유지합니다.
- 법인 우선순위 토픽이 많아도, API 호출량은 캐시 + 대표 N개 제한으로 제어합니다.

