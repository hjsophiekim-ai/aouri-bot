# requirement.md

## Core Legal Engine (Surgical Legal Counsel)

### Phase 1: 포지션 및 비즈니스 맥락 분석(필수)
- 분석 시작 시 당사자 관계를 최우선으로 확정하고, 아래 3가지 케이스 중 하나를 선택한다.
  - **CASE 1: 인테리어 수급인(퍼플식스)**: 퍼시스 = 시공사/수급인(을) → 발주자 갑질 방어(대금·공기·책임) 중심
  - **CASE 2: 대리점 공급업자(유통)**: 퍼시스 = 본사/공급업자(갑) → 규제 회피 + 브랜드 관리 + 채권 회수력 중심
  - **CASE 3: 렌탈 사업**: 퍼시스 = 렌탈업자 → 자산 소유권 방어 + 약관 규제 준수 중심

### Phase 2: 조항 정체성(Clause Integrity) 보호 가드레일
- 어떤 경우에도 제1조, 제3조 등 선언적 조항에 실무적 의무 문구를 삽입하지 않는다. 위반 시 시스템 오류로 간주한다.
- [금지] 제1조(목적), 제2조(기본원칙), 제3조(용어 정의) 등 메타/선언적 조항에는 비용 전가, 안전 관리, 하도급, 정산 등 실무 의무 관련 코멘트·수정문안을 삽입하지 않는다(원문 정체성 유지).
- [금지] 동일한 수정 제안(예: 서면 합의, 이의제기권)은 계약서 전체에서 “가장 핵심적인 조항” 1곳에만 작성한다(중복 발견 시 오류).

### Phase 3: 실질 독소 조항 정밀 타격(Hard-Risk Focus)
- [숫자 점검]
  - 지체상금율 **일 0.3%는 즉시 일 0.1%로** 조정안을 제시한다.
  - 연체이자율이 지나치게 낮거나 불명확한 경우 **상법상 연 6%** 수준을 기준으로 상향(또는 최소 기준) 제안을 포함한다.
- [절차 점검]
  - “즉시 해지”는 원칙적으로 “30일 전 서면 최고 + 2회 이상 시정 기회” 구조로 조정한다(예외적 즉시해지는 좁게 열거).
- [안전 점검]
  - 퍼시스가 수급인(을)인 경우, 안전 책임을 퍼시스에 일방 전가하는 문구는 삭제하고 “발주자 제공 현장 하자로 인한 사고는 면책(또는 감경)” 단서를 포함한다.

### Phase 4: 자가 검증(Audit) 및 필터링
- 최종 출력 전 아래 3개 질문에 모두 적합해야 한다.
  - 목적 조항이 깨끗한가? (Yes만 허용)
  - 퍼시스가 수급인인데 퍼시스에게 불리한 의무를 AI가 추가하지 않았는가? (No만 허용)
  - 중복되는 코멘트가 있는가? (No만 허용)

## Strategic Legal Counsel (퍼시스 그룹) 요구사항

### 1) 포지션별 검토 전략(Phase 1)
- 분석 시작 시 반드시 아래 3가지 시나리오 중 1개를 확정하고, 그 포지션에 맞는 방향으로만 검토/수정안을 생성한다.
  - **[판매대리점/유통] 퍼시스 = 공급업자(갑)**: 대리점법 준수(경영간섭·가격강제 방지) + 채권 회수력(정산/증빙/상계) 강화
  - **[퍼플식스 인테리어] 퍼시스 = 수급인(을)**: 발주자 갑질 방어(대금지연/부당감액/과도 지체상금) + 지체상금(0.1% 이하) 감경 + 안전 책임 전가 차단
  - **[가구 렌탈] 퍼시스 = 렌탈업자**: 자산 소유권 보호(임의처분 금지) + 약관법/소비자보호(위약금 상한·청약철회 보장) 준수

### 2) 조항 정체성(Identity) 보호 원칙(Phase 2)
- 제1조(목적), 제3조(정의) 등 선언적 조항에 비용/안전/정산 등 실무 의무를 삽입하는 코멘트·수정문안을 생성하지 않는다.
- 모든 리스크 코멘트/수정문안은 해당 주제를 다루는 **가장 직접적인 조항 1곳**에만 1회 작성한다(중복 삽입 금지).
- 단순 키워드 반응형 템플릿 삽입을 금지하고, 조항의 법적 기능과 분쟁 포인트에 맞춘 최소 변경 원칙을 적용한다.

### 3) 출력 품질 기준
- “HIGH” 등급 리스크는 계약서 전체에서 5개 이내로 제한한다.
- 문장은 법률 전문가가 직접 작성한 수준으로 간결·정제된 표현을 사용한다.

---

## Strategic Review Logic (시니어 사내 변호사 — Legal Intelligence Engine)

> **적용 범위**: `clause_level.py` 및 모든 리뷰 엔진의 최상위 실행 가이드.
> 기존의 키워드 기반 자동 삽입(Keyword-to-Template Mapping) 로직을 금지한다.
> 모든 계약서는 조항의 **법적 성격**과 **우리 측 포지션**을 기준으로만 분석한다.

### Phase 1: 당사자 지위 및 전략 확정 (Side Determination)

1. **퍼시스 = 공급업자(갑)** (대리점/유통 계약):
   - 대리점법·공정거래법 위반 회피(경영간섭·가격강제·불이익 제공 방지)
   - 채권 회수 권리 방어(정산/증빙/상계) 중심
2. **퍼시스 = 수급인(을)** (인테리어/공사/용역 계약):
   - 발주자(갑) 귀책 면책, 지체상금 감경(일 0.1% 이하), 대금 청구권 확보 중심
3. **퍼시스 = 렌탈업자**:
   - 자산 소유권 방어(임의처분 금지), 약관법/소비자보호 준수 중심

### Phase 2: 조항 정체성 보호 (Clean Clause Rule)

- **[절대 금지]** 제1조(목적), 제2조(기본원칙), 제3조(용어 정의) 등 선언적 조항에 실무 의무(비용, 안전, 정산 등) 문구를 삽입하지 않는다. 원문을 유지하거나 오타만 수정한다.
  - `clause_level.py`: `_is_hard_block_clause`가 article 1/2/3을 하드 블록 처리함으로써 구현.
- **[절대 금지]** 조항 내용과 무관한 코멘트를 삽입하지 않는다.
  - 예: 대금수금(제6조)에 판촉비 서면합의 문구 삽입 금지
  - 예: 사업장 소재지 조항에 비용전가 코멘트 삽입 금지
  - 구현: `payment_settlement` 주입 시 `_SETTLEMENT_GUARD` 내용 가드 적용.

### Phase 3: 실질 리스크 정밀 타격 (Expert Risk Targeting)

1. **[가격 구속 — 최우선]**: 대리점 계약에서 '가격 승인/지정/통제' 문구가 있으면 즉시 **재판매가격 유지행위(공정거래법 제46조) 리스크로 식별** → HIGH/MUST.
   - `_has_price_approval_risk()` 함수가 조 번호보다 내용을 우선하여 감지.
   - '승인' → '권장가 가이드라인(참고용)' 수정안 제시. 가격 강제·불이익 조치 금지 문구 명시.
2. **[수치 점검]**: 지체상금 일 0.3%는 즉시 일 0.1%로 조정 제안. 연체이자율 불명확 시 상법상 연 6% 기준 제안.
3. **[절차 점검]**: '즉시 해지' → '30일 서면 최고 및 2회 시정 기회 부여'로 통일.

### Phase 4: 자가 검증 및 중복 제거 (Self-Audit)

1. 동일 주제 코멘트/수정안이 3회 이상 반복되면 가장 핵심적인 조항 1곳만 남기고 나머지를 `dedup_suppressed` 처리한다.
   - `_dedup_rewrite_suggestions()` 및 `_suppress_secondary()` 함수로 구현.
2. UI 화면과 Word 다운로드 파일의 내용이 100% 일치하도록 데이터 동기화 로직을 유지한다.
   - `clause_results`가 단일 소스(API 응답)이며, Word 작성 시 동일 데이터를 사용해야 한다.

---

## Advanced Strategic Logic (시니어 사내 변호사 — Surgical Contract Intelligence)

> **적용 범위**: `clause_level.py` `build_clause_level_result` 진입 시 최우선 실행.
> 기존의 모든 키워드 반응형 템플릿(Keyword-Triggered Templates)을 폐기한다.
> 계약서의 '제목'과 '대가 관계'를 분석하여 아래 상호 배타적 검토 엔진을 가동한다.

### Phase 1: 계약 유형 확정 (Classification First)

- `build_clause_level_result` 진입 직후 WordprocessingML 검사 다음으로, 다른 로직보다 먼저 `_classify_contract_type`을 호출하여 `_contract_class`를 확정한다.
- `_contract_class` 값: `"advisory"` | `"rental"` | `"construction"` | `"project_installation"` | `"general"`
- 확정된 `_contract_class`를 이후 모든 분기(리스크 패턴, AI 프롬프트, 필터 체인)의 공통 기준으로 사용한다.
- **[비활성화]** 계약 포지션 자동 추론 및 UI 출력("1-0) 계약 성격 및 우리 측 포지션 분석" 섹션) 기능을 비활성화한다. 대체 생성 금지.

### Phase 2: 로직 오염 원천 차단 (Logic Isolation — Hard-Block)

- 현재 분석 중인 계약 유형과 무관한 타 사업부(렌탈, 물류, B2C 약관 등)의 로직 주입을 기술적으로 금지한다.
- `[advisory/개발 계약 Hard-Block]` — 제목에 '자문', '용역', '개발'이 포함된 경우:
  - **생성 금지 텍스트**: '렌탈', 'B2C 약관', '채권추심', '부동산', '물류' 관련 모든 문구
  - 구현: `_FORBIDDEN_ADVISORY_KW` 패턴 + `_apply_zero_hallucination_guardrail` 함수

### Phase 3: 자문/개발 계약 전문 변호사급 핵심 리스크 타격 (Surgical Review)

퍼시스가 비용(예: 1억 원)을 지급하는 '갑(위탁자)'인 경우, 아래 3개가 누락되면 **CRITICAL** 리스크다.

1. **지식재산권 귀속 — CRITICAL**
   - 산출물의 모든 권리는 **위탁자(퍼시스)에게 전적으로 귀속**되어야 함.
   - 수탁자(교수 등)에게 귀속되거나 퍼시스에게 이용권만 주는 조항은 반드시 수정 제안.
   - 법적 근거: 저작권법 제9조(업무상저작물)는 도급 계약에서 수탁자 귀속을 원칙으로 하므로, 명시적 위탁자 귀속 규정이 필수.
   - 구현: `_apply_advisory_ip_review` → IP 귀속 탐지 → `_IP_FURSYS_REWRITE` 수정문안 삽입
2. **제3자 권리 침해 보증 — CRITICAL**
   - "수탁자는 결과물이 제3자의 지재권을 침해하지 않았음을 보증하며, 문제 발생 시 퍼시스를 면책하고 모든 손해를 배상한다"는 문구를 필수 삽입.
   - 구현: `_IP_WARRANTY_REWRITE` 수정문안
3. **배상 한도 예외 단서 — HIGH**
   - 손해배상 한도가 '용역비'로 제한된 조항에는 '지재권 침해/비밀유지 위반/고의중과실 시 무제한 배상' 단서 삽입.
   - 구현: `_LIABILITY_CAP_KW` 탐지 → `_LIABILITY_CAP_EXCEPTION_REWRITE` 삽입

### Phase 4: 조항 정체성 수호 (Clean Clause Rule)

- 제1조(목적), 제2조(기본원칙), 제3조(정의) 등 선언적 조항에는 어떠한 실무 의무(정산, 안전, 판촉 등)도 삽입하지 않는다.
- 해당 조항은 원문대로 두거나 문구만 정제한다.
- 구현: `_is_hard_block_clause` (article 1/2/3 하드블록) + `_apply_zero_hallucination_guardrail`

---

## Section Removal Specs

### [REMOVED] 1-0) 계약 성격 및 우리 측 포지션 분석

- **UI 출력 제거**: 해당 섹션 렌더링 블록 전체 삭제. 대체 섹션 생성 금지.
- **LLM 프롬프트**: 해당 heading 및 관련 지시문 삭제.
- **Summary generation pipeline**: 해당 node 제거. 포지션 자동 추론 기능 자체 비활성화.
- **JSON schema**: 관련 필드 제거.
- 계약 포지션 자동 추론 기능 전체 비활성화. 어떤 형태로도 재생성 금지.

### [REMOVED] 5) 관련 법령

- **법령 검색 retrieval pipeline 비활성화**: `law_service.search_for_review` 호출 중단.
- **Case law retrieval 제거**: 판례 검색 로직 전체 제거.
- **법령 citation 생성 로직 제거**: LLM이 법령·판례·행정해석을 자동 생성하는 로직 비활성화.
- **UI 섹션 제거**: "관련 법령" 렌더링 블록 전체 삭제.
- **Prompt template**: 법령 관련 지시문 삭제.
- **System prompt 추가 제약**: `"명시적으로 요청되지 않은 경우 법령, 판례, 행정해석을 생성하거나 추론하지 말 것."`
- 구현 대상: `clause_level.py` law search 호출 블록, AI system prompt, 관련 UI 컴포넌트.

---

## Service Agreement: Prepayment Risk Analysis

> 적용 계약 유형: 용역계약 / 자문계약 / 컨설팅계약 / 개발계약 (`_contract_class == "advisory"`)

### 탐지 조건 (아래 중 하나라도 충족 시 HIGH risk)

- 선급금 존재
- 계약 초기에 30% 이상 지급
- 결과물 제출 전 지급 존재
- 장기 프로젝트 계약
- 단계형 용역 계약

### 자동 검토 항목 (탐지 시 아래 5개 항목 누락 여부 점검)

1. 선급금 보증보험증권 존재 여부
2. 단계별 산출물 제출 조건 존재 여부
3. 검수/승인 후 지급 구조 여부
4. 미완성 시 환급 조항 존재 여부
5. 중도 해지 시 기성고 정산 기준 존재 여부

- 위 항목 누락 시: 누락 항목 수에 따라 HIGH 또는 MEDIUM 권고 생성.
- 구현: `_detect_prepayment_risk()` — 원문 조항 직접 탐지 기반. 추론 금지.

---

## Service Agreement: Payment Structure Recommendations

> 용역대금을 분할 지급하는 계약에서 선급금 비율이 높거나 결과물 제출 전 지급되는 경우 자동 생성.

### 우선순위별 수정 권고

**1순위 — 선급금 보증보험증권 요구**
```
위탁자는 선급금 지급 전 수탁자로부터 선급금 상당액의
이행(선급금)보증보험증권을 제출받을 수 있다.
```

**2순위 — 단계별 검수 후 지급 구조**
```
각 단계별 결과물 제출 및 위탁자의 검수·승인 완료 후
해당 단계 대금을 지급한다.
```

**3순위 — 중도 해지 시 미완성 대금 환수**
```
수탁자의 귀책으로 계약이 중도 종료되는 경우,
미완성 부분에 해당하는 선급금은 즉시 반환하여야 한다.
```

- 위 권고는 용역/자문/개발/컨설팅 계약에서 우선 출력한다.
- 원문에 해당 구조가 이미 존재하는 경우 해당 항목 권고 생성 금지.

---

## Strict Relevance Filter

계약 원문에 존재하지 않는 산업/거래 구조를 추론하여 삽입하지 말 것.

**삽입 금지 키워드 목록** (원문 계약서에 없으면 관련 리스크 분석 생성 금지):

- 렌탈
- 가맹
- 하도급
- B2C
- 리스
- 보험
- 의료
- 부동산
- 금융

구현: `_STRICT_RELEVANCE_FORBIDDEN` 패턴 — 원문 계약서 전체 텍스트에 위 키워드가 없는 경우, 해당 주제의 리스크 분석·수정 제안 생성을 차단한다.

---

## Hallucination Prevention

모든 리스크 분석은 반드시 아래 중 하나에 근거해야 한다:

1. **계약서 명시 조항** — 원문에 직접 존재하는 조항
2. **계약 구조상 직접 도출 가능한 리스크** — 계약 구조(지급방식, 기간, 당사자 관계)에서 논리적으로 도출되는 리스크
3. **실제 존재 조항** — 지급 / 검수 / 손해배상 / 지식재산권 등 원문에 실재하는 조항

**금지 사항**:
- 계약서 원문에 근거 없는 사실 생성 금지
- 근거 없는 업종 추론 금지
- 원문에 없는 당사자·거래 구조·산업 관행 추론 후 삽입 금지

구현: AI system prompt에 아래 제약 추가.
```
계약서 원문에 존재하지 않는 사실·업종·거래구조를 추론하여 리스크 분석에 삽입하지 말 것.
모든 리스크 지적은 (1) 원문 명시 조항, (2) 계약 구조 직접 도출 리스크,
(3) 지급/검수/손해배상/지재권 등 실제 존재 조항 중 하나에만 근거할 것.
```

---

## Review Philosophy — "틀린 걸 많이 말하지 않는 AI"

> 현재 시스템은 "많이 검토하는 AI" 방향으로 동작하고 있다.
> 실제 좋은 계약검토 AI는 **"틀린 걸 많이 말하지 않는 AI"**다.
> 적게 지적하더라도 진짜 위험한 것만 정확히 짚는 구조로 전환한다.

**시스템 정체성 재정의**:
- 기존: 문장 수정형 AI (rewrite-heavy)
- 목표: **Risk Detection AI + Clause Recommendation AI**

**운영 원칙**:
- 원문 rewrite 최소화
- 리스크 탐지 중심
- 추가 조항 권고 중심
- 지적 수는 적더라도 정확도 우선

---

## Review Priority Engine

> 기존 법률 키워드 기반 리스크 탐지를 중단한다.
> **계약 운영상 실제 회사 손실 가능성** 기준으로 우선순위를 재설계한다.

### LEVEL 1 — 실제 금전 손실 위험 (HIGH 우선 표시 의무)

아래 항목이 존재하면 반드시 HIGH risk로 우선 표시한다.

| 항목 | 설명 |
|------|------|
| 선급금 미회수 | 미이행 시 선급금 환수 구조 부재 |
| 검수 없는 지급 | 결과물 확인 없이 대금 지급 |
| 중도해지 정산 부재 | 해지 시 기성고 정산 기준 없음 |
| 미완성 위험 | deliverable 불완전 시 처리 기준 없음 |
| 일정 지연 | 납기 지연에 대한 패널티·대응 기준 없음 |
| deliverable 불명확 | 결과물 정의·형태·범위 미명시 |
| 책임 제한 과도 | 위탁자 손해 회복 불가 수준의 배상 상한 |

### LEVEL 2 — 권리 확보 위험 (MEDIUM)

| 항목 |
|------|
| 지식재산권 귀속 |
| 사용권 범위 |
| 재사용 제한 |
| 비밀유지 의무 |

### LEVEL 3 — 일반 법률 문구 (출력 조건부)

- 민법 일반론, 선언적 조항, 추상적 판례
- **실제 리스크가 없으면 출력 금지**
- LEVEL 1이 존재하는 경우 LEVEL 3 항목은 suppressed 처리

### 우선순위 집행 규칙

1. LEVEL 1 리스크가 1개라도 존재하면 HIGH risk로 최상단 출력
2. LEVEL 3는 원문에 실질적 분쟁 소지가 없으면 생성 금지
3. 동일 계약에서 HIGH는 최대 5개로 제한 (초과 시 LEVEL 1 기준 상위 5개만 유지)

---

## Service Contract Mandatory Checklist

> 적용: 용역 / 자문 / 컨설팅 / 개발 계약 (`_contract_class == "advisory"`)
> 아래 9개 항목을 반드시 점검하고, 누락 발견 시 수정 권고를 생성한다.

| # | 점검 항목 | 누락 시 등급 |
|---|-----------|-------------|
| 1 | 선급금 비율 명시 여부 | HIGH |
| 2 | 검수 후 지급 구조 여부 | HIGH |
| 3 | 단계별 deliverable 존재 여부 | HIGH |
| 4 | 결과물 승인권(위탁자) 명시 여부 | MEDIUM |
| 5 | 미완성 시 환수 가능 여부 | HIGH |
| 6 | 기성고 기준 정산 조항 여부 | MEDIUM |
| 7 | 일정 지연 대응 조항 여부 | MEDIUM |
| 8 | 결과물 재수정 의무 조항 여부 | MEDIUM |
| 9 | 용역 종료 후 결과물 활용 가능 범위 | MEDIUM |

- 원문에 해당 구조가 명시되어 있으면 해당 항목 권고 생성 금지
- 구현: `_check_service_contract_checklist()` — 원문 직접 탐지. 추론 금지.

---

## Output Format Policy — No Inline Rewrite

> 기존의 regex 기반 inline 문장 수정 방식을 전면 중단한다.
> 계약 원문 훼손 방지.

### 금지 방식 (즉시 중단)

- regex 기반 inline merge
- token patching
- substring overwrite
- partial sentence replacement

### 신규 방식 (의무 적용)

1. **원문 계약 조항은 절대 수정하지 않는다.**
2. **원문 전체를 그대로 유지한다.**
3. **수정 제안은 "추가 조항" 형태로만 생성한다.**
4. 삭제·수정이 필요한 경우에도 원문 보존 + 변경 제안만 별도 표시

### 출력 형식 예시

```
[원문 유지]
수탁자는 각 자문 단계별로 다음의 결과물을 편집 가능한 PPT 형태로 제출하여야 한다.

[추가 권고]
"위탁자는 각 단계 결과물의 검수 완료 후 해당 단계 대금을 지급한다."
```

- `suggested_rewrite` 필드에 원문 그대로 유지 + `[추가 권고]` 블록 append 방식으로 구현
- `changed_segments`는 추가된 권고 텍스트만 `inserted_segment`로 표시
- 원문 삭제·수정 세그먼트(`deleted_segment`) 생성 금지

---

## Project Installation Contract Architecture

> **적용 범위**: 장비 공급 + 설치 + 시운전이 포함된 계약 (`_contract_class == "project_installation"`)
> 단순 물품매매계약으로 분류하지 않고 **설치형 프로젝트 계약**으로 재분류하여 산업안전 중심 검토를 수행한다.

### 분류 기준 (키워드 탐지)

`_PROJECT_INSTALL_KW` 패턴이 계약서 제목·본문(상위 300자)·파일명에서 하나라도 탐지되면 `project_installation`으로 확정한다.

| 탐지 키워드 |
|-------------|
| 설치 |
| 시운전 |
| 현장 작업 |
| 자동화 설비 |
| 생산 라인 |
| 공장 |
| SmartFactory / Smart Factory |
| commissioning |
| setup |
| integration |

- **분류 우선순위**: `project_installation` → `advisory` → `rental` → `construction` → `general` 순서로 검사한다.
- 법령 DB 검색 유형: `"설치시운전_산업안전중대재해"`

### 13대 HIGH 우선 검토 리스크 영역

설치형 프로젝트 계약에서 아래 조항이 기존 원문에 존재하더라도, 내용이 불리하거나 불명확하면 HIGH 리스크로 식별·수정 제안한다.

| # | 검토 항목 | 리스크 설명 |
|---|-----------|-------------|
| 1 | 납기·설치완료 기준 | 준공 기준 불명확 시 분쟁 |
| 2 | 성능 보증 기간 및 범위 | 장비 결함·성능 미달 책임 귀속 |
| 3 | 시운전 완료 기준 | 합격 기준 미명시 시 무한 보완 |
| 4 | 인수인계 절차 | 갑의 일방적 거부 가능성 |
| 5 | 지체상금 상한 | 일 0.3% 초과 시 즉시 감경 제안 |
| 6 | 장비 소유권 이전 시점 | 대금 완납 전 위험 부담 |
| 7 | 하자보수 기간 및 범위 | 과도한 무상 A/S 의무 |
| 8 | 손해배상 한도 | 계약금액 초과 배상 리스크 |
| 9 | 불가항력 면책 | 자연재해·외부 요인 면책 범위 |
| 10 | 설계 변경 절차 | 갑의 일방적 변경 지시 차단 |
| 11 | 대금 지급 조건 | 검수 거부 시 대금 지연 위험 |
| 12 | 계약 해지 절차 | 정당 사유 없는 즉시 해지 차단 |
| 13 | 분쟁 해결 조항 | 관할 법원·중재 기관 명시 여부 |

---

## Mandatory Safety Review Logic

> **적용 범위**: `_contract_class == "project_installation"`
> 아래 10개 안전 항목이 원문에 없으면 **반드시 HIGH 권고**를 생성한다.
> 구현: `_apply_project_installation_checklist()` → `_PROJECT_INSTALL_SAFETY_ITEMS`

| # | 항목 ID | 항목명 | 탐지 조건 (원문 미포함 시) | 등급 |
|---|---------|--------|--------------------------|------|
| 1 | `pi_safety_responsibility` | 안전 책임 주체 명시 | "안전 책임", "안전관리 주체" 미포함 | HIGH |
| 2 | `pi_safety_manager` | 안전관리자 지정 의무 | "안전관리자 지정", "안전담당자" 미포함 | HIGH |
| 3 | `pi_legal_compliance` | 산안법·중대재해처벌법 준수 의무 | "산업안전보건법", "중대재해" 미포함 | HIGH |
| 4 | `pi_subcontractor_safety` | 하도급 안전관리 연대책임 | "하도급+안전", "협력업체+안전" 미포함 | HIGH |
| 5 | `pi_work_stop_right` | 긴급 작업 중지권 | "작업 중지", "작업중지권" 미포함 | HIGH |
| 6 | `pi_risk_assessment` | 위험성 평가 실시 의무 | "위험성 평가" 미포함 | HIGH |
| 7 | `pi_accident_reporting` | 사고 발생 즉시 보고 의무 | "사고+보고", "즉시+보고" 미포함 | HIGH |
| 8 | `pi_ppe_education` | 안전장비·교육 제공 의무 | "안전장비", "보호구", "안전교육" 미포함 | HIGH |
| 9 | `pi_access_control` | 현장 출입 통제 및 구역 관리 | "출입 통제", "현장 출입" 미포함 | HIGH |
| 10 | `pi_commissioning_accident_liability` | 시운전 중 사고 책임 귀속 | "시운전+사고", "시운전+책임" 미포함 | HIGH |

- 모든 안전 항목은 `is_checklist_item=True`, `must_fix=True`, `approval_required=True`로 생성한다.
- `is_checklist_item=True` 항목은 Review Priority Engine의 HIGH 5개 캡(cap) 계산에서 제외된다.

---

## Mandatory Training & Operation Review

> **적용 범위**: `_contract_class == "project_installation"`
> 아래 8개 교육·운영 항목이 원문에 없으면 권고를 생성한다.
> 구현: `_apply_project_installation_checklist()` → `_PROJECT_INSTALL_TRAINING_ITEMS`

| # | 항목 ID | 항목명 | 등급 |
|---|---------|--------|------|
| 1 | `pi_train_user` | 사용자(운용자) 교육 제공 의무 | HIGH |
| 2 | `pi_train_admin` | 관리자 교육 제공 의무 | HIGH |
| 3 | `pi_train_maintenance` | 유지보수 담당자 교육 의무 | MEDIUM |
| 4 | `pi_train_emergency` | 비상 대응 절차 교육 의무 | HIGH |
| 5 | `pi_ops_manual` | 운용 매뉴얼 납품 의무 | HIGH |
| 6 | `pi_korean_manual` | 한국어 매뉴얼 제공 의무 | MEDIUM |
| 7 | `pi_retrain_support` | 재교육 지원 의무 (인수 후 6개월) | MEDIUM |
| 8 | `pi_sla` | 유지보수 SLA (4시간 대응·24시간 복구) | MEDIUM |

- HIGH 항목: `must_fix=True`, `approval_required=True`
- MEDIUM 항목: `must_fix=False`, `approval_required=False`
- 모든 항목: `is_checklist_item=True` (HIGH cap 제외)

### 필터 체인 실행 순서 (업데이트)

```
1. Zero-Hallucination Guardrail
2. Advisory IP & Copyright Review
3. Rental Filter
4. Domestic Filter
5. Clause Integrity Filter
6. Sidiz Position Strategy
7. Global Sentence Dedup
8. Service Contract Checklist (advisory 전용)
9. Project Installation Checklist (project_installation 전용)  ← NEW
10. Review Priority Engine (HIGH cap: 체크리스트 제외)  ← UPDATED
11. No Inline Rewrite Policy
```

---

## Changelog

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-05-11 | Project Installation Contract 분류 추가 (`project_installation`), 안전 10개·교육 8개 체크리스트 추가, HIGH cap에서 `is_checklist_item` 제외 |
| 2026-05-07 | docx 다운로드 soft MEDIUM 수정본 생성 실패 버그 수정 (must_fix/approval_required 없는 MEDIUM은 suggested_rewrite 불필요) |
| 2026-05-07 | xlsx 파일 업로드 지원 추가 (openpyxl 기반) |
