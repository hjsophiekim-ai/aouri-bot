# 204) domestic_korea vs cross_border 분류 레이어 추가

## 목표

- 국내 대리점 계약에서도 “다국가 거래 분쟁조항 점검(ACT-004)”이 우선 적용되는 문제를 방지한다.
- 해외 정황이 있을 때만 cross-border 분쟁 리스크(집행/비용/기간)를 reasoning에 포함한다.

## 판별 요소(휴리스틱)

- 당사자/법인 형태: Inc/LLC/Ltd 등 해외 법인 토큰
- 관할/준거법 조항의 언어: 영문 비중, foreign governing law 힌트
- 해외 정황: 국가명, 해외/국외/수출입, Incoterms, 외화(USD/EUR/JPY 등)
- 파일명 힌트: 영문/overseas/international 등

## 판정 결과

- `domestic_korea`
- `cross_border`
- `foreign_entity_involved`

각 판정은 `evidence`를 함께 반환한다.

## 적용 정책

### 1) domestic_korea

- 해외 집행/다국가 분쟁 reasoning 금지
- ACT-004가 매칭되더라도:
  - 위험도를 HIGH로 보지 않고 완화(MEDIUM)
  - 설명을 “국내 분쟁조항 점검(전속관할/합의관할/민사소송법상 관할)” 중심으로 변경

### 2) cross_border / foreign_entity_involved

- ACT-004(다국가 분쟁조항 점검) 로직을 그대로 적용(준거법/관할 또는 중재 + 집행 리스크 고려)

## 변경 위치

- 분류기: [jurisdiction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/jurisdiction.py)
- ACT-004 국내 완화: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)

