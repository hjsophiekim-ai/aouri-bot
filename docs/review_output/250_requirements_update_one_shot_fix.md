# 250. Requirements 업데이트(one-shot dealer precision)

## 업데이트 요구사항
- R1. user_focus precedence
  - 사용자가 입력한 중점 이슈(user_focus_issues)를 최우선으로 조항에 매핑하고, 매핑 결과(목적별 후보 조항)를 결과/Word에 표시한다.
- R2. dealer/distributor priority requirement
  - dealer/distributor 계약에서는 불이익·지위남용 → 경영간섭 → 해지 남용 → 비용전가 → 정산/상계 → 개인정보/운영 → 분쟁(관할/준거법) 순으로 검토/노출한다.
- R3. domestic dealer dispute de-prioritization
  - 국내 대리점 계약에서 제27조/분쟁조항은 보조 이슈로만 처리한다(사용자 요청/크로스보더 예외).
- R4. termination clause redline requirement
  - 제23조(특히 즉시해지)는 termination 축으로 고정하고, 시정기회/객관화/무최고 해지 좁게 열거 등 전용 redline candidate를 생성한다.
- R5. MEDIUM concrete rewrite in Word
  - MEDIUM 조항도 Word(DOCX)에 제안 문안(구체 문구)을 반드시 포함한다.
  - 문구(suggested_rewrite/reference_rewrite)가 없으면 문서 생성은 실패 처리한다.
- R6. UI/Word single source of truth
  - UI 렌더링과 Word 생성은 동일 canonical 결과를 사용하며, UI-visible 조항/문안이 Word에 누락되면 실패 처리한다.
- R7. canonical result persistence
  - deep review 완료 시 canonical 결과를 세션에 저장하고 재사용한다.
  - 재생성은 rebuild 모드에서만 허용한다.
- R8. dealer AI deep review selection
  - dealer 계약에서 AI deep review selector는 핵심 조항(21/23/14/11/17/8~10)과 user_focus 매핑 조항을 최우선으로 선정하고, 국내+비요청 분쟁조항은 감점한다.

