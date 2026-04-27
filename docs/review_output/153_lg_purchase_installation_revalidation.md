# 153) LG 장비공급/설치/시운전 계약 재검증(수정 후)

요청된 “실제 LG 계약서(docx)” 파일은 현재 작업 디렉터리에서 확인되지 않아, 본 문서는 레포에 포함된 회귀 픽스처(`runtime/tests/fixtures/lg_purchase_installation.txt`) 기반으로 엔진 동작을 재검증한 결과를 기록합니다.

---

## 1) review posture 확인

- 입력:
  - entity=퍼시스
  - contract_type=장비공급/설치/시운전
  - text=lg_purchase_installation.txt
- 결과:
  - `review_posture = buyer_favorable`
  - `party_role.our_role = buyer`

출력 예(로컬 실행 결과):
- posture buyer_favorable
- party_our_role buyer

---

## 2) 질문이 계약유형에 맞게 달라지는지

생성된 질문(최대 5개):
- Q-CA-002-liability-cap
- Q-CA-003-indemnity-procedure
- Q-CA-008-subcontract-approval
- Q-CA-004-privacy-delegation
- Q-CA-999-template-owner

특히 설치/현장 작업 컨텍스트에서 “재위탁 사전 승인/안전 책임”을 묻는 질문이 포함됩니다.

---

## 3) clause별 검토/수정이 되는지

메타:
- clause_count: 5
- issue_clauses: 3

---

## 4) 관련 법령이 무관 영역(대리점법 등)으로 확산되지 않는지

purchase_installation 프로파일에서는 계약 전체 쿼리에서:
- `민법/상법/산업안전보건법/중대재해처벌법/제조물책임법`을 우선 토픽으로 사용
- `대리점법`은 기본 억제

---

## 5) 조항 제목과 수정문안 매핑 정확성

엔진 보호:
- 조항 추출 단계에서 clause_id 중복이 발생하면 자동 disambiguate(`.D2` 등)
- clause_level 단계에서 clause_title mismatch가 발견되면 `docx_allowed=false`로 block 처리

---

## 6) Word redline 표시(변경 부분만)

로컬 생성된 docx의 `document.xml` run 분석 결과:
- 빨간색 run: 6
- 일반 run: 45

즉, 변경 run과 변경 없는 run이 공존하여 “문단 전체가 통째로 빨갛게 보이는” 현상을 완화했습니다.

---

## 7) 실제 docx 파일 기반 재검증을 위해 필요한 것

요청하신 “LG 장비공급/설치 계약서(원본 docx)”를 아래 경로로 제공하면, 업로드→질문→review→docx 다운로드까지 end-to-end로 재검증을 완료하고 본 문서를 실제 계약서 기준으로 업데이트합니다.

- 권장 위치: `docs/review_input/`
- 예시 파일명: `LG_장비공급설치_계약서_TrackChanges.docx`

