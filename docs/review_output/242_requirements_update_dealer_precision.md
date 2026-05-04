# 242. Requirements 업데이트(dealer precision)

## 범위
- 대리점/유통(dealer/distributor) 계약에서 우선순위/토픽 분류/Word 출력/단일 소스/검증 규칙을 최신 요구사항으로 정리한다.

## 신규/수정 Requirements
- R1. Dealer/distributor 우선순위 강제
  - 불이익 제공/지위 남용 → 경영간섭 → 해지 남용 → 비용전가 → 정산/상계 → 개인정보/운영 → 분쟁(관할/준거법) 순으로 검토/노출한다.
- R2. 국내 대리점 분쟁조항 보조화
  - 국내 대리점 계약에서는 분쟁해결/관할/준거법(예: 제27조)을 1차 핵심 이슈로 올리지 않는다.
  - 단, 사용자가 분쟁을 명시적으로 요청했거나 cross-border 정황이 있으면 예외로 허용한다.
- R3. User focus issue precedence
  - 사용자가 입력한 중점 검토 이슈(user focus)를 최우선으로 조항에 매핑하고 상단 노출/문안 생성에 반영한다.
- R4. Clause topic isolation(오염 차단)
  - 해지(termination) 조항이 분쟁(dispute) 토픽으로 잘못 분류되어 “답변 반영 쟁점/핵심 이슈”가 전이되지 않도록 분류 우선순위/보정 규칙을 둔다.
- R5. Dealer-law core clause escalation
  - 대리점 계약의 핵심 조항(제21/23/14/11/17 및 정산 8~10)은 guidance가 아니라 구체 redline candidate(제안 문안) 생성 대상으로 승격한다.
- R6. Word에 구체 제안 문안 필수 포함
  - Word(DOCX)에는 조항별로 “원문 핵심 표현/제안 문안/수정 이유/관련 법령/기준”을 반드시 출력한다.
  - HIGH가 아니더라도 MEDIUM 조항은 “제안 문안”을 반드시 포함한다.
  - 본문 redline이 없더라도 “조항별 구체적 수정안 부록”은 항상 생성한다.
  - Word에 사유만 있고 문구(제안 문안)가 없으면 문서 생성은 실패 처리한다.
- R7. UI/Word single source of truth + consistency check
  - UI, DOCX generator, appendix, summary는 동일 canonical review result를 사용한다.
  - “앱에는 있는데 Word에는 없음” 또는 조항 집합/문안 누락/불일치가 발생하면 DOCX 생성 실패 처리하며, mismatch 상세를 오류로 반환한다.

