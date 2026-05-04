# 203) 계약유형/거래구조 선분류 기반 엔진 보정(근본 원인 수정)

## 문제

- 계약유형/거래구조가 충분히 확정되기 전에 rule pack / rewrite 문구가 기계적으로 적용되어 다음 문제가 발생했다.
  - 국내 대리점 계약 분쟁조항에 “다국가 거래 분쟁조항 점검” 논리(해외집행/다국가 분쟁)가 섞임
  - 분쟁조항에 판촉비/광고비/반품비(비용전가) 문구가 삽입됨
  - 개인정보 조항에 설치/현장/산안법/작업중지권 문구가 반복 삽입됨
  - 질문 엔진이 계약유형과 무관한(설치/현장/다국가/안전) 질문을 우선 제시함

## 핵심 원인

- 계약 전체 컨텍스트(국내/해외/혼합, 계약유형)와 조항 주제(분쟁/개인정보/정산/안전 등)가 “조항별 rewrite 적용”보다 앞에서 확정되지 않았다.
- 조항별 rule 매칭에서 `context_text`가 넓게 합쳐져 인접 조항 키워드가 섞이면서 오탐이 발생했다.
- AI rewrite가 켜진 경우에도 조항 주제와 무관한 문구가 삽입되는 것을 막는 안전장치가 부족했다.

## 수정 방향(정책)

1) 계약을 먼저 분류한다.
- 국내 계약 / 해외 계약 / 혼합 거래(외화/해외 지급/해외 설치/해외 서비스/영문 계약/해외 법인 정황 등)
- 대리점/위탁거래 / 앱개발 / 물품구매·설치 / 개인정보처리위탁 등

2) 그 다음에 계약유형별 핵심 이슈만 우선 적용한다.

3) 조항 주제와 무관한 rewrite 문안은 절대 삽입하지 않는다(guardrail).

4) 동일 문구 반복 삽입을 억제한다(대표 1회 + 나머지 guidance).

5) 질문도 계약서 핵심 리스크를 기준으로 3~5개만 묻는다.

## 구현 요약(이번 변경의 “근본 레이어”)

- **거래구조(국내/해외) 분류 레이어 추가**
  - `domestic_korea / cross_border / foreign_entity_involved` 판정 및 evidence 포함
  - 위치: [jurisdiction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/jurisdiction.py)
- **국내 계약에서 ACT-004(다국가 분쟁) 과도 적용 방지**
  - 국내로 판정되면 ACT-004는 위험도/설명을 국내형으로 완화
  - 위치: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)
- **조항 주제 분류 + rewrite 호환성(compatibility) 가드레일**
  - 분쟁조항에는 분쟁(준거법/관할/중재/조정) 외 문구 금지
  - 개인정보 조항에는 산안법/현장/작업중지권 문구 금지(정황 있을 때만 예외)
  - 대리점 계약에는 SOW/SBOM/오픈소스 문구 유입 차단(정황 있을 때만 예외)
  - 위치: [clause_topic.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_topic.py), [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- **조항별 rule 매칭에서 context 오염 축소**
  - rule trigger 매칭은 `title + clause_text` 중심으로 하고, 짧은 context만 제한적으로 사용
  - 위치: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)

