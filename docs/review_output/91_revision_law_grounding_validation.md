# /api/revision/suggest_text 수정 제안 + 법령 근거 결합 검증

## 확인 항목
- 원문 조항
- 검출 issue
- 적용 rule
- law_search 또는 관련 법령 근거
- 수정 제안 이유(suggested_direction)
- fallback_text 또는 AI 보강 문안
- approval_required 여부

## 호출 결과
- ok: `true` / http_status: `200` / elapsed_client_sec: `0.9563`

## 입력(샘플)
- entity: `퍼시스` / contract_type: `대리점/위탁/유통`
- text: `제1조(비용 부담) 대리점은 판촉비, 광고비 및 반품 비용을 전적으로 부담한다. 제2조(기타) 본 계약은 당사와 대리점 간 대리점 거래를 규율한다.`

## 응답 요약
- law_search_present: `true` / enabled: `true`
- ai_present: `false`
## 1) 첫 번째 이슈 조항(요약)
- 원문 조항: `"제1조(비용 부담) 대리점은 판촉비, 광고비 및 반품 비용을 전적으로 부담한다."`
- 검출 issue: `["대리점 비용전가(원상회복/판촉/반품/광고비 등) 탐지", "대리점 비용부담 트리거(승인 필요)"]`
- 적용 rule: `["RISK-006", "ACT-009"]`
- 수정 제안 방향: `["대리점 비용전가 항목을 상한/정산 기준/증빙/사전합의로 제한"]`
- fallback_text_present: `true`
- approval_required: `true`

