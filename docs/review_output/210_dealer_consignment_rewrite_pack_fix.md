# 210) 대리점/위탁거래 rewrite pack 정교화(포함/제외 준수)

## 목표

- 대리점/위탁거래 계약에서 “진짜 중요한 조항”만 정교하게 수정되게 한다.
- 아래 문구가 정황 없이 섞이지 않게 차단한다.
  - SOW / 오픈소스 / SBOM / 설치·현장안전 / 산안법 / 작업중지권

## 포함(대리점 핵심)

- 비용전가(판촉비/광고비/반품비/원상회복)
- 정산/공제/상계
- 계약해지/불이익 조치
- 분쟁해결(국내 기준)
- 개인정보/재위탁(있는 경우만)

## 구현 포인트

### 1) 계약유형 오염 방지(대리점 ↔ 앱개발)

- 대리점 계약이고 강한 app_dev 정황이 없으면 `APP-*` 룰을 매칭 결과에서 제거한다.
- 위치: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py) <mccoremem id="01KQ8NQ0SWK281S63E2K603W52" />

### 2) 조항 주제 기반 적용 제한

- 비용전가(RISK-006/ACT-009)는 비용/정산/대리점 토픽에서만 적용
- 정산(C-001)은 정산/비용 토픽에서만 적용
- 위치: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)

### 3) rewrite 호환성 가드레일(분쟁/개인정보/안전)

- 분쟁조항에는 비용전가·안전 문구를 금지
- 개인정보 조항에는 산안법/작업중지권 등을 금지
- 위치: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 4) 대리점 핵심 rewrite 보강

- 비용전가: [RISK-006 rewrite](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py#L221-L255)
- 정산(산식/공제사유/증빙/기한): [C-001 rewrite](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py#L646-L675)

