# 아우리봇 요구사항 명세서

## [Core Review Logic]

기존 규칙 기반 리뷰 엔진은 `runtime/rules/` 의 YAML 룰셋과 `clause_level.py` 의 조항 분석 파이프라인으로 구성된다.

---

## [Basic Requirements] 다운로드 DOCX 출력 기본 요구사항
> 최종 업데이트: 2026-05-07
> 적용 파일: `runtime/review/docx_writer.py`

### DOCX 표 테두리 (Table Borders)

- **요구사항**: 최종 수정본 DOCX 다운로드 시 생성되는 모든 표는 반드시 테두리(외곽선 + 내부 구분선)를 표시한다.
- **대상**: `9) 조항별 구체적 수정안 부록` 표 및 `10) High risk / Approval required 표` 포함, `_tbl()` 함수로 생성되는 모든 표
- **구현**: `_tbl()` 내 `tblPr` 에 `tblBorders` 요소를 추가하여 6방향 모두 단선(`single`) 테두리 적용

```
테두리 스펙:
  val   = "single"   (단선)
  sz    = "4"        (0.5pt, 8분의 1pt 단위)
  space = "0"
  color = "000000"   (검정)
  적용 방향: top / left / bottom / right / insideH / insideV
```

---

## [Advanced Review Logic]
> 최종 업데이트: 2026-05-07
> 적용 파일: `runtime/review/clause_level.py`

기존의 키워드 매칭 기반 템플릿 삽입 로직을 폐기하고, 아래 지능형 필터링 로직을 적용한다.
각 필터는 `build_clause_level_result` 내 2차 dedup(`_apply_article_dedup_and_consolidation`) 이후에 순서대로 실행된다.

---

### 1. 계약 유형별 'Exclusive' 필터링

#### [Rental Filter] — `_apply_rental_filter()`
- **조건**: 계약서 제목 또는 본문에 `렌탈`, `구독`, `임대차`, `Lease` 단어가 없는 경우
- **동작**: 렌탈 관련 코멘트(소유권, 위약금, 임대, 리스, 반납, 구독 해지 등) 생성을 **기술적으로 차단(Hard-Block)**
- **출력**: `suggested_rewrite = null`, `guardrail_block.filter = "rental_filter"`

#### [Domestic Filter] — `_apply_domestic_filter()`
- **조건**: 당사자가 모두 한국 법인이고 외국 법인 마커가 없는 경우
- **동작**: `dispute` 토픽 조항에서 `다국가 거래`, `국제 관할`, `해외 집행`, `cross-border` 등 문구가 포함된 코멘트 생성 금지
- **결과**: 관할 조항은 `risk_tier = LOW`, `must_fix = false` 로 강제

---

### 2. 조항 정체성(Clause Integrity) 검증 로직 — `_apply_clause_integrity_filter()`

각 조항의 제목·토픽과 `suggested_rewrite` 내용이 일치하는지 검증한다.

| 조항 토픽 | 제목 힌트 | 삽입 금지 문구 |
|---|---|---|
| `personal_data` | 개인정보 | 정산, 상계, 공제, 판촉비, 장려금 |
| `damage` | 손해배상, 책임제한, 배상 | 판촉비, 증빙, 광고비, 장려금 |

- **원칙**: 코멘트는 해당 주제를 다루는 '가장 본질적인 조항' 1곳에만 작성
- **위반 시**: `suggested_rewrite = null`, `guardrail_block.filter = "clause_integrity"`

---

### 3. 포지션별 타격 전략 (Sidiz Case) — `_apply_sidiz_position_strategy()`

**적용 조건**: entity에 `시디즈`/`SIDIZ` 포함 + Sidiz가 위탁자(갑) 포지션인 경우

| 시나리오 | 조항 토픽/제목 | 추가 내용 |
|---|---|---|
| ① CI/SI 위반 | termination, CI, SI, 브랜드, 상표 | 즉시 해지권 + 위약벌(계약금액 [ ]%) 명시 |
| ② 개인정보 유출 | personal_data, 개인정보 | 무제한 구상권(배상금·과태료 전액) 확보 |
| ③ 정산 이의제기 | payment_settlement, 정산, 상계 | 7일 이내 서면 이의 기간 명시 + 간주 동의 |

- ①②: `risk_tier = HIGH`, `must_fix = true`, `approval_required = true`
- ③: `risk_tier = MEDIUM`, `review_tier = SUGGEST`

---

### 4. 중복 제거 엔진 (Global Deduplication) — `_apply_global_sentence_dedup()`

- 동일한 문장(정규화 후 완전 일치, 20자 이상)이 전체 리포트에서 2회 이상 발견되면
- 두 번째 출현부터 해당 문장을 `상기 제{article_number}조 참조` 로 대체
- 한국어 문말어미(다/않겠다/니다) 기준으로 문장 분리

---

### 필터 실행 순서

```
build_clause_level_result()
  ...
  _apply_article_dedup_and_consolidation()  # 2차 dedup
  # ── Advanced Review Logic + Zero-Hallucination Guardrail ──
  _apply_zero_hallucination_guardrail()     ← 최우선 실행
  _apply_rental_filter()
  _apply_domestic_filter()
  _apply_clause_integrity_filter()
  _apply_sidiz_position_strategy()
  _apply_global_sentence_dedup()
  # ── 최종 change_record 재계산 ──
```

---

## [Zero-Hallucination Guardrail]
> 최종 업데이트: 2026-05-07
> 적용 파일: `runtime/review/clause_level.py`
> 함수: `_apply_zero_hallucination_guardrail()`
> **실행 우선순위: 모든 필터보다 먼저 실행 (최우선)**

키워드 매칭 기반 로직이 유발하는 '로직 오염(hallucination)'을 원천 차단하는 전역 가드레일.

---

### 규칙 1: 제1·2·3조 절대 보호 (모든 계약 유형)

- **조건**: `article_number` ∈ {1, 2, 3} (목적·일반원칙·용어정의 조항)
- **동작**: `suggested_rewrite = null`, `risk_tier = LOW`, `must_fix = false`
- **이유**: 선언적 조항은 실질 리스크가 없으며, 수정안 삽입 시 계약서 문맥 오염

---

### 규칙 2: [If Service/Advisory] 금지 키워드 Hard-Block

**감지 조건**: `contract_type` 또는 본문 400자 이내에 아래 단어 포함  
→ `자문 | 용역 | Service | Advisory | 컨설팅 | 위임 | Engagement | 집필 | 강의 | 연구`

**Hard-Block 대상** (자문/용역 계약에서 `suggested_rewrite`·`rewrite_reason` 포함 시 즉시 차단):

| 금지 패턴 | 차단 사유 |
|---|---|
| `렌탈` | 자문 계약과 무관 |
| `소유권은 퍼시스에` | 물품공급 전용 문구 |
| `물류시설` | 물류/임대 전용 문구 |
| `구독 서비스` | 렌탈/구독 계약 전용 |
| `소유권 존속` | 할부/물품 계약 전용 |
| `채권추심` | 금융 계약 전용 |
| `위약금 10%` | 무관한 위약금 산식 |
| `임대차 보증금 / 보증금 반환` | 부동산 임대차 전용 |

**동작**: `suggested_rewrite = null`, `guardrail_block.filter = "advisory_forbidden_keywords"`

---

### 규칙 3: [If Service/Advisory] 무관 법령 인용 금지

자문/용역 계약에서 인용 금지 법령 목록:

- `물류시설법` · `부동산세법` · `화물자동차 운수사업법`
- `주택임대차보호법` · `상가건물 임대차보호법` · `임대차보호법`
- `전자상거래법` · `방문판매법` · `할부거래법`

**허용 법령**: 민법(도급/위임 규정), 부정경쟁방지법, 저작권법, 개인정보보호법, 근로기준법

**동작**: `related_laws` 내 해당 법령 항목 삭제, `suggested_rewrite` 내 관련 문장 제거

---

### 자가 감사(Audit) 규칙 (AI 시스템 프롬프트 반영)

1. "지금 자문 계약서인데 렌탈 이야기를 한 마디라도 섞었는가?" → Yes면 즉시 제거
2. "인용한 법령이 이 계약 내용과 단 1%라도 접점이 있는가?" → No면 법령 삭제

---

---

## [Expert Advisory Review Logic]
> 최종 업데이트: 2026-05-07
> 적용 파일: `runtime/review/clause_level.py`
> 함수: `_classify_contract_type()` / `_apply_advisory_ip_review()`
> **실행 우선순위: Zero-Hallucination Guardrail 다음 (2순위)**

### Phase 1: 계약 유형 엄격 분류 (Strict Classification)

`_classify_contract_type(contract_type, text, filename)` → `"advisory" | "rental" | "construction" | "general"`

| 유형 | 감지 키워드 | 동작 |
|---|---|---|
| `advisory` | 자문, 용역, Advisory, 교수, 강의, 집필, 연구용역, 컨설팅, 위임, 디자인 용역, 컨텐츠 제작 | IP/저작권 전용 로직 실행, 키워드→템플릿 루프 격리 |
| `rental` | 렌탈, 임대차, Lease, 구독 | Rental 전용 로직 |
| `construction` | 공사, 인테리어, 시공, 건설, 리모델링 | 안전·현장 전용 로직 |
| `general` | 그 외 | 기존 대리점/물품 로직 유지 |

**[격리 원칙]**: `advisory` 유형으로 분류되면 키워드→템플릿 이어붙이기 루프를 완전히 건너뛴다.  
대신 `_apply_advisory_ip_review()`가 IP 전용 검토를 수행한다.

---

### Phase 2: IP & Copyright 핵심 타격 로직

`_apply_advisory_ip_review()` — 자문/용역 계약 전용

#### ① IP가 수탁자 귀속 → **CRITICAL 플래그**

- **탐지**: 조항 제목/본문에 `지식재산권 | 저작권 | 성과물 | 결과물 | 산출물 | 지재권 | IP | 소유권` 포함 + `수탁자에게 귀속 | 을에게 귀속 | 이용권만 부여 | 비독점 이용` 패턴
- **동작**: `risk_tier = HIGH`, `must_fix = true`, `approval_required = true`, `ip_critical = true`
- **수정안**: 퍼시스 전적 귀속 + 독점 무제한 이용권 + 수탁자 3자 제공 금지

> 1억 이상 대가 계약(`1억|100,000,000|일억|자문료.*억`)이면 리스크 가중 표시

#### ② IP 조항 있으나 제3자 보증 누락 → **HIGH**

- **수정안**: "수탁자는 제3자 권리 침해 없음을 보증, 분쟁 시 자신의 비용으로 면책·배상"

#### ③ IP 전용 조항 자체 없음 → **CRITICAL (첫 실질 조항에 삽입)**

- 제1·2·3조 제외한 첫 조항에 IP 귀속 + 제3자 보증 양식 통합 삽입

---

### Phase 3: 법령 인용 정밀도

자문/용역 계약에서 허용 법령: **저작권법, 부정경쟁방지법, 민법(위임·도급)**  
금지 법령: Zero-Hallucination Guardrail의 `_FORBIDDEN_LAW_KW` 규칙 그대로 적용

---

### Phase 4: 자가 검증 (Internal Audit) — AI System Prompt 반영

```
1. "자문/개발 계약인데 저작권 귀속 문제를 지적했는가?" → No라면 수정 제안 추가
2. "제3자 권리 침해 보증 문구를 넣었는가?" → No라면 삽입 제안 추가
3. "렌탈이나 부동산 법령이 섞여 있는가?" → Yes라면 즉시 삭제
```

---

### 필터 실행 순서 (갱신)

```
build_clause_level_result()
  ...
  _apply_article_dedup_and_consolidation()      # 2차 dedup
  # ── 계약 유형 분류 ──
  _classify_contract_type()                     # advisory/rental/construction/general
  [if not advisory] 키워드→템플릿 루프          # advisory면 skip
  # ── 필터 체인 ──
  _apply_zero_hallucination_guardrail()         # 1순위
  _apply_advisory_ip_review()                   # 2순위 (advisory 전용)
  _apply_rental_filter()
  _apply_domestic_filter()
  _apply_clause_integrity_filter()
  _apply_sidiz_position_strategy()
  _apply_global_sentence_dedup()
  # ── 최종 change_record 재계산 ──
```

---

## [Exclusive IP Review Engine]
> 최종 업데이트: 2026-05-07
> 적용 파일: `runtime/review/clause_level.py`
> **실행 우선순위: Expert Advisory Review Logic과 동일 레이어 (Zero-Hallucination 다음)**

### Step 1. 계약 유형별 로직 격리 (Hallucination Block)

**감지 조건**: 계약서 제목 또는 `contract_type`에 `자문`, `용역`, `개발`, `제작` 포함

**Hard-Block 대상** (자문/개발 계약에서 생성 절대 금지):

| 차단 문구 | 차단 사유 |
|---|---|
| `렌탈` | 자문·개발 계약과 무관 |
| `소유권 존속(퍼시스 외)` | 물품 계약 전용 |
| `채권추심` | 금융 계약 전용 |
| `부동산` | 부동산 계약 전용 |
| `물류` | 물류·운송 계약 전용 |

**법령 교체**: 자문/개발 계약에서 아래 법령을 삭제하고 허용 법령으로 교체한다.

| 삭제 법령 | 교체 법령 |
|---|---|
| `부동산세법`, `물류시설법` | `저작권법`, `부정경쟁방지법`, `특허법` |

---

### Step 2. 개발/자문 계약 핵심 타격 포인트 (Mandatory Checks)

**적용 조건**: 퍼시스가 대금을 지급하는 위탁자(갑)인 경우

#### ① [지식재산권 귀속] — CRITICAL

- **탐지**: IP 소유권을 수탁자(교수, 개발사 등)에게 귀속하는 조항
- **동작**: `risk_tier = HIGH`, `must_fix = true`, `approval_required = true`
- **수정안**: 위탁자(퍼시스) 전적 귀속 + 독점 무제한 이용권 + 수탁자 제3자 제공 금지

#### ② [제3자 권리 침해 보증] — HIGH

- **탐지**: IP 조항이 있으나 제3자 침해 보증 문구 누락
- **수정안**: "수탁자는 결과물이 제3자의 지적재산권을 침해하지 않았음을 보장하며, 문제 발생 시 전적인 책임을 진다"

#### ③ [배상 한도 예외 단서] — HIGH

- **탐지**: 배상 범위를 '용역대금 총액' 등으로 제한하는 조항 (`손해배상`, `배상`, `책임제한` 제목 포함)
- **동작**: 아래 예외 단서 추가 제안
- **수정안**: "단, 지식재산권 침해, 비밀유지의무 위반, 고의·중과실로 인한 손해의 경우에는 위 배상 한도의 제한을 받지 아니하며, 수탁자는 실제 발생한 손해 전액을 배상한다."

---

### Step 3. 조항 정체성 및 중복 제거 (Clean Output)

- **[금지]**: 제1조(기본원칙), 제2조(목적) 등 선언적 조항에 실무 의무(정산, 안전 등)를 넣지 않는다.
- **[금지]**: 동일한 코멘트를 여러 조항에 반복하지 않는다. 대표 조항 1곳에서만 설명한다.

---

### 필터 격리 원칙 (Loop Isolation)

키워드→템플릿 이어붙이기 루프는 **Advisory/개발 계약에서 완전히 건너뛴다(`if _is_advisory_class: continue`)**.  
렌탈 관련 템플릿은 `_contract_class == "rental"` 또는 `"general"` 계약에서만 호출된다.

---

## [Changelog]

| 날짜 | 변경 내용 |
|---|---|
| 2026-05-07 | Advanced Review Logic (필터 1~4) 추가, clause_level.py 적용 |
| 2026-05-07 | Zero-Hallucination Guardrail 추가 (제1·2·3조 보호, Advisory 금지키워드, 무관법령 차단) |
| 2026-05-07 | Expert Advisory Review Logic 추가 (계약 유형 분류, IP CRITICAL 점검, 키워드 템플릿 루프 격리) |
| 2026-05-07 | Exclusive IP Review Engine 추가 (부동산·물류 Hard-Block, 법령 교체, 배상한도 예외 단서) |
