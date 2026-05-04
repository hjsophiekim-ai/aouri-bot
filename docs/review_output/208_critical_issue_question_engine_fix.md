# 208) 질문 엔진 개선(계약서 핵심 리스크 중심 3~5개)

## 목표

- 질문을 계약유형/거래구조에 맞게 “핵심만” 3~5개로 줄인다.
- 설치/현장/안전 질문은 해당 정황이 실제 있을 때만.
- cross-border 질문은 해외 정황이 있을 때만.
- 질문마다 reason_code를 남긴다(tags에 `reason_code:*` 포함).

## 구현

### 1) 계약 프로파일 기반 분기

- 계약 프로파일 추론: [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)
- 대리점/위탁거래(`dealer_consignment`)는 전용 질문 세트를 사용한다.
- 위치: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py#L107-L350)

### 2) 대리점/위탁거래 핵심 질문(최대 5)

- 상대방 양식 여부
- 판촉비/광고비/반품비/원상회복 비용부담(상한·증빙·정산)
- 정산식/상계/공제(차감) 기준 및 절차
- 해지/물량 축소/불이익 조치 요건 및 절차
- 개인정보 처리 정황이 있을 때만 개인정보 질문 추가

### 3) 질문 수 제한

- 질문 생성 단계에서 `max_questions=5`로 제한.
- 위치: [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L92-L103)

