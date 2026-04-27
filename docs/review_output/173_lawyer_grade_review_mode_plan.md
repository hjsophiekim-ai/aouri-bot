# 173) Lawyer-grade review mode 계획

## 목표(요구사항 재정의)
- 변호사 검토 수준의 “정밀 리뷰”를 목표로, 계약 상황(당사자 역할/거래 구조/업종/상대방 규모/첨부파일/질의응답)을 종합 반영
- 조항별 산출물(문제 인식 → 법령/판례 grounding → 최소 변경 redline → 수정 이유)을 안정적으로 생성
- 출력 정책(리스크 티어):
  - HIGH: redline(필수 수정)
  - MEDIUM: blue guidance(방향 제안)
  - LOW: 참고 메모(기본 숨김 가능)

## 전체 구조(2단계 + 컨텍스트 통합)
### 0) 입력 컨텍스트 레이어
- 계약 텍스트 + 파일명/첨부(가능하면 별도 텍스트 추출)
- Q&A(질의응답) + 당사자 역할 추론 결과
- 계약유형(contract_type) + 업종/엔티티(entity)

### 1) 전 조항 스크리닝(Deterministic/Rule/Law 기반)
- 목적: “전 조항을 빠르게” 위험도/누락을 걸러내고, deep review의 대상 후보를 좁히기
- 구성:
  - 조/항/호/목 기반 계층형 clause extraction
  - 규칙 매칭 및 risk tier 산정(approval_required/high_risk 포함)
  - (선택) 중요 조항 키워드 기반 우선순위 부여
  - (선택) clause-level law_search(시간/비용 예산 내에서 deep review 대상 우선)
- 산출:
  - clause_results(스크리닝 결과)
  - meta.tier_counts, clause_count, warnings

### 2) AI deep review(고위험/중위험/핵심조항)
- 목적: 변호사식 “정확한 문제/정확한 문장/최소 변경”을 만드는 정밀 단계
- 입력:
  - 원문 + 상위 컨텍스트(context_text)
  - 스크리닝 결과(이슈/규칙/초기 제안/방향)
  - 관련 법령/판례 후보(가능한 경우)
  - Q&A/당사자 역할/검토 posture(구매자/판매자 유리)
- 출력(조항별):
  - rewrite_reason(정밀한 사유)
  - suggested_rewrite(최소 변경 redline을 만들기 좋은 문장)
  - (확장안) issue_reasoning / legal_basis(reason_code) / fallback_to_guidance 플래그

## Lawyer-grade 품질을 올리는 추가 설계(다음 단계)
- “계약 상황” 반영 강화
  - answers를 단순 참고가 아니라, 프롬프트에서 우선순위와 조항별 판단에 직접 반영(예: 산출물 귀속/소스코드 인도/유지보수 범위 등)
  - 상대방 규모/거래 구조(원도급/하도급/재위탁) 등 시나리오 파라미터화
- Law grounding 고도화
  - contract_type별 query template 세분화(민법 도급/저작권/개인정보/부정경쟁 등)
  - time_budget을 “deep review 대상 우선”으로 재배분
  - 결과 re-rank 및 저관련 제거(현재보다 더 강한 필터)
- 최소 변경(redline) 최적화
  - “덧붙임”보다 “치환/삭제/짧은 문장 삽입”을 기본으로
  - 문장 후처리(법무 문체/조사/중복/메타표현 제거) 일관 적용
- Word 결과물 품질
  - 본문: HIGH만 redline(삭제=취소선, 추가=빨강)
  - 별도 섹션: MEDIUM/LOW guidance(blue)
  - 부록: 변경 핵심 표현/이유/법령 근거를 자연어로 요약

## 실제 코드 수정 계획(이번 목표에 직접 연결)
### A. “전체 스크리닝 → AI deep review”를 표준 파이프라인으로 고정
- 변경 포인트: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - 스크리닝 결과 기반으로 AI deep review 대상 조항 동적 선택
  - AI deep review 적용 여부를 응답에 표시

### B. 세션 리뷰(업로드→리뷰)도 analyze와 동일 품질로 동기화
- 변경 포인트: [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L131-L181)
  - 기존: law_service/ai_provider 미사용
  - 목표: analyze와 동일하게 AI/Law 적용 + ai meta 포함

### C. 계약유형별 핵심 조항 우선순위 반영
- 구현 방향:
  - 앱개발: 목적/수행/검수/지연/결과물귀속/3자권리/보안/개인정보/해지/분쟁
  - 장비구매/설치: 검수/하자/안전/지체/책임제한/보증/해지/관할
  - deep review 선택 점수에 반영(키워드 기반 + risk tier)

### D. deep review 대상 수 동적 조정 + 응답 표시
- 구현 방향:
  - 계약 길이(clauses 수) + risk 분포(must/medium) 기반으로 deep review 대상 수 계산
  - 응답 표시:
    - meta.ai.selected_clause_ids / selected_count
    - clause_results[].ai_deep_reviewed

