# 154. Why LG Review Was Not Good Enough

## 관찰된 구조적 원인(현재 코드 기준)
- 1) party orientation 실패: 계약서에서 구매자/공급자 역할을 정확히 분해하는 레이어가 없고, posture는 계약유형/키워드 기반 heuristic이다.
- 2) clause identity mismatch: clause_id/제목은 텍스트 패턴 기반이라, 원본 문서 스타일/번호 체계가 복잡하면 매핑이 흔들릴 수 있다(불일치 시 docx 생성 실패로 방어).
- 3) law grounding mismatch: entity 우선 토픽에 의해 무관 법령이 섞일 수 있었고, 컨텍스트 기반 필터/리랭크를 추가했으나 issue-type 템플릿 기반 좁은 검색은 추가 개선 여지가 있다.
- 4) rewrite genericity: 템플릿 복붙을 제거하고 조항 기반 패치로 전환했지만, 실제 법무 품질은 더 많은 rule_id별 패치/역할(구매자/공급자) 인식이 필요하다.
- 5) redline granularity 실패: 줄 단위 강조에서 토큰 diff 기반 run 생성으로 개선했지만, 문장/항목 단위 구조를 더 정교히 보존할 필요가 있다.
- 6) docx readability 문제: clean copy 반복을 제거하고(변경 조항만) 표지/요약/부록/표 구조로 재구성했으나, 상대방/계약명 등 메타데이터 입력 수집을 더 강화해야 한다.
