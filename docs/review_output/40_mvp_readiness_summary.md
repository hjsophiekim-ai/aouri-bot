# AouriBot MVP Readiness Summary (33~39 종합)

## 근거 문서
- [33_sample_review_test_1.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/33_sample_review_test_1.md)
- [34_real_contract_review_5cases.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/34_real_contract_review_5cases.md)
- [35_batch_review_20cases.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/35_batch_review_20cases.md)
- [36_entity_rule_comparison.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/36_entity_rule_comparison.md)
- [37_risk_rule_accuracy_test.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/37_risk_rule_accuracy_test.md)
- [38_api_quality_check.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/38_api_quality_check.md)
- [39_mvp_gap_analysis.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/39_mvp_gap_analysis.md)

## 1) 현재 가능한 기능
- 계약 텍스트 입력 시 rule 기반 검토 실행(`/api/review/analyze`)
  - matched_rules / checklist_rules / approval_required_matches 반환
  - backlog는 판정에서 제외하고 참고로만 포함
- 질문/답변(룰 기반) 세션 + 답변 반영(review context 확장)
- 검토 결과 저장/조회(관리자 조회 포함), 승인대기함 분리
- EP Mock 화면에서 세션 시작/상태 전이/결재 handoff(stub/http 지점) 시연 가능
- 템플릿 기반 초안 생성(LLM 없이) + 조항별 수정 제안 “뷰”(redline 아님)

## 2) 현재 부족한 기능
- 문맥 이해 부재로 인한 오탐/미탐 한계(키워드 기반)
- 조항 구조화/정규화 취약(표/별첨/정의/상호참조)
- 법인별 특화 정책을 “판정 차이”로 반영하는 로직이 제한적(동일 문구에 대해 entity별 결과가 크게 달라지지 않음)
- 일부 핵심 위험 문구 커버리지 부족(테스트에서 미탐 존재)
  - 대리점 비용전가: FAIL (2/2)
  - 안전책임 공백/안전책임 일방전가: FAIL (2/2, high/approval로 승격되지 않음)
- 운영 관측/품질관리 체계 부족(골든셋, 회귀 테스트, 통계/리포트 표준화)

## 3) 실무 테스트 가능한 범위
- “키워드 기반 1차 스크리닝” 및 체크리스트 생성
  - 무제한 책임/일방 면책/기술자료 요구/하도급 단가감액은 테스트에서 탐지 PASS
- 법무팀이 계약서 1건을 넣고:
  - 어떤 규칙이 걸렸는지(근거/추천 조치) 확인
  - 승인 필요(approval_required) 여부로 우선순위 라우팅
- 전제 조건
  - 본 결과는 법률 자문/판정이 아니라 “리스크 후보 탐지 + 체크리스트”로만 사용

## 4) 바로 EP에 붙여도 되는 부분
- EP → AouriBot 세션 시작/상태 전이/결재 전환 지점(Stub) 자체는 MVP 시연 가능
- Admin 기반 rule 조회/버전 확인/Backlog 분리 조회
- 업로드/질문/검토/수정제안/초안 생성 “패널 UX” 형태

다만 EP 실연동(실 결재, 실 DB/권한/감사)은 별도 준비가 필요하다.

## 5) AI API 없이는 안 되는 부분
- 문맥 기반 의미 판정(면책 범위, carve-out, 제한/예외 조합 등)
- 조항 리라이팅 기반의 redline/대체조항 “자동 생성”
- 리스크 설명/요약의 고품질 자연어 생성(법무 보고서급)
- 유사 케이스/내부 기준/판례 매칭(검색+요약)

## 6) 우선순위별 다음 단계
1. 안정화(치명 이슈)
   - 핵심 위험 문구 미탐(대리점 비용전가, 안전 책임) 보완
   - 응답에 high_risk/approval_required 플래그와 최소 “issue” 구조를 추가해 소비측 혼선을 줄임
2. 룰 품질/검증
   - 골든셋(라벨링) 구축 + 회귀 테스트 자동화
   - 계약유형/법인별 스코프 정교화(불필요한 매칭 억제)
3. 조항 구조화
   - 조항 파서/타입 분류 + 조항별 판정(“문장 매칭”에서 “조항 단위”로 이동)
4. 워크플로우/운영
   - 사람 검토 UI/히스토리/승인 정책 정교화
5. AI 도입
   - 설명 생성 → 수정 문안 생성 → redline(가드레일/검증 포함) 순으로 단계적 도입

## 7) go / hold / no-go 판단
### GO (즉시 가능)
- 내부 데모/PoC: 업로드 → 질문 → review analyze → (수정제안/초안) → 승인/법무 라우팅
- 법무팀 “관찰형 평가”: 결과를 참고자료로만 사용(결재 자동화 금지)

### HOLD (조건부 진행)
- 법무팀 파일럿(실제 업무 투입에 준하는 평가)
  - 조건: 핵심 미탐 보완 + 골든셋 기반 최소 정확도 기준 정의 + 감사/보안/권한 설계 확정

### NO-GO (현 단계에서 금지)
- 자동으로 “법무 승인/결재 승인” 판단을 대체하는 사용
- redline 자동 생성 후 무검토 반영(사람 검토 없이 적용)
- 문맥 기반 법률 판단(면책 유효성/책임 범위 확정 등)을 rule 결과로 단정

