# 235. Dealer/Distributor 계약 검토 Requirements 업데이트

## 신규/수정 Requirements
### R1. 사용자 중점 검토 이슈 최우선 반영
- 사용자 입력 `review_focus`는 세션에 저장되고, 구조화된 objective로 변환되어 조항별 `user_focus_hit` 및 우선순위에 반영되어야 한다.
- 탐지 실패 시 “탐지 없음”으로 종료하지 말고, 후보 조항과 탐지 실패 가능 원인을 표시해야 한다.

### R2. 계약유형별 이슈 우선순위 적용
- 계약 프로파일(contract_profile)에 따라 조항 정렬/AI shortlist/질문 생성의 우선순위를 다르게 적용해야 한다.

### R3. Dealer/Distributor 전용 review policy(하드 룰)
- dealer/distributor 계약에서는 다음 우선순위를 하드 적용한다.
  1) 불이익 제공 / 거래상 지위 남용
  2) 경영간섭 / 영업자율 침해
  3) 계약해지 / 물량축소 / 공급중단 / 불이익 조치 남용
  4) 비용전가 / 판촉비 / 광고비 / 반품비 / 원상회복 비용
  5) 정산 / 상계 / 공제 / 증빙
  6) 개인정보 / 고객정보 / 교육 / 운영협의(정황 있을 때)
  7) 분쟁조항 / 관할 / 준거법(보조)
- 제27조 분쟁조항은 대리점 핵심 조항 검토가 끝난 뒤에만 보조적으로 다룬다.

### R4. dealer 핵심 조항 항상 포함
- 룰 매칭이 없더라도 최소한 다음 조항은 결과에 포함되어야 한다.
  - 제21(불공정행위), 제23(해지), 제14(경영간섭), 제11/17(비용), 제8~10(정산), 제27(분쟁) (+ 제2~3)

### R5. clause-specific redline requirement
- 제21/제23 등 실무상 중요한 조항은 “추상적 방향”이 아니라 바로 적용 가능한 구체 문안(suggested_rewrite)을 생성해야 한다.

### R6. reasoning quality requirement
- 이유(rewrite_reason)는 조항 맞춤형으로 작성해야 하며,
  - 불이익 제공/지위 남용, 경영간섭, 비용전가, 정산 통제, 해지 남용 등과의 연결을 명시해야 한다.
- 관할 조항에는 불필요한 과잉 reasoning(해외 집행 등)을 금지한다.

### R7. UI/Word single source of truth requirement
- UI clause cards, revision output, Word docx는 동일한 canonical clause_results를 사용해야 한다.
- UI에 있는 조항이 Word에 없거나(또는 반대) mismatch가 나면 파일 생성은 실패 처리하고 diagnostics를 제공해야 한다.

