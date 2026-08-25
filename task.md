# 아우리봇 태스크 관리

## 완료된 태스크

### [DONE] Advanced Review Logic 구현 (2026-05-07)

**목표**: 키워드 반응형 `suggested_rewrite` 생성 로직을 지능형 필터 기반으로 전환

**변경 파일**:
- `requirement.md` — [Advanced Review Logic] 섹션 신규 작성
- `runtime/review/clause_level.py` — 5개 필터 함수 추가 + `build_clause_level_result` 호출 지점 삽입

**추가된 함수**:

| 함수명 | 역할 |
|---|---|
| `_is_rental_contract()` | 렌탈 계약 여부 판별 |
| `_is_domestic_only()` | 국내 전용 계약 여부 판별 |
| `_apply_rental_filter()` | 비렌탈 계약의 렌탈 관련 코멘트 Hard-Block |
| `_apply_domestic_filter()` | 국내 계약의 국제 관할 리스크 코멘트 차단 |
| `_apply_clause_integrity_filter()` | 조항 정체성 위반(크로스 토픽 오염) 차단 |
| `_apply_sidiz_position_strategy()` | 시디즈 위탁자 포지션 전략 주입 |
| `_apply_global_sentence_dedup()` | 전역 문장 중복 → '상기 제N조 참조' 대체 |

**적용 위치**: `build_clause_level_result()` 내 2차 `_apply_article_dedup_and_consolidation()` 이후

---

### [DONE] Expert Advisory Review Logic 구현 (2026-05-07)

**목표**: Advisory/용역 계약 유형 격리, IP 귀속 CRITICAL 점검, 키워드→템플릿 루프 폐기

**변경 파일**:
- `requirement.md` — [Expert Advisory Review Logic] 섹션 신규 작성
- `runtime/review/clause_level.py` — 4개 상수·2개 함수 추가, 루프 격리 가드 삽입

**추가된 함수/상수**:

| 항목 | 역할 |
|---|---|
| `_classify_contract_type()` | advisory/rental/construction/general 엄격 분류 |
| `_apply_advisory_ip_review()` | IP 귀속 CRITICAL + 제3자 보증 점검 |
| `_LARGE_PAYMENT_KW` | 1억 이상 고액 대가 감지 |
| `_IP_CONTRACTOR_KW` | 수탁자 귀속 패턴 감지 |
| `_IP_WARRANTY_KW` | 제3자 침해 보증 패턴 감지 |

**키워드→템플릿 루프 격리**: `_is_advisory_class` 플래그로 Advisory 계약에서 `continue` 처리

---

### [DONE] Zero-Hallucination Guardrail 구현 (2026-05-07)

**목표**: 자문/용역 계약에서 렌탈·물류시설 등 무관 문구 오염 원천 차단

**변경 파일**:
- `requirement.md` — [Zero-Hallucination Guardrail] 섹션 신규 작성
- `runtime/review/clause_level.py` — `_is_service_advisory_contract()` + `_apply_zero_hallucination_guardrail()` 추가, 필터 체인 최우선 삽입

**추가된 함수**:

| 함수명 | 역할 |
|---|---|
| `_is_service_advisory_contract()` | 자문/용역 계약 감지 |
| `_apply_zero_hallucination_guardrail()` | 제1·2·3조 보호 + 금지키워드 Hard-Block + 무관 법령 삭제 |

**적용 위치**: 모든 필터 중 최우선 실행 (2차 dedup 직후)

---

### [DONE] DOCX 표 테두리 적용 (2026-05-07)

**목표**: 최종 수정본 다운로드 DOCX의 `9) 조항별 구체적 수정안 부록` 표 테두리 미표시 버그 수정

**변경 파일**:
- `requirement.md` — [Basic Requirements] DOCX 표 테두리 섹션 신규 작성
- `runtime/review/docx_writer.py` — `_tbl()` 함수에 `tblBorders` 추가

**변경 내용**: `_tbl()` 내 `tblPr`에 6방향 단선 테두리(`single`, sz=4, color=000000) 추가. `9) 부록` 및 `10) High risk` 표 포함 모든 표에 일괄 적용.

---

## 진행 중인 태스크

(없음)

---

## 예정 태스크

- [ ] Sidiz 포지션 전략 — CI/SI 위약벌 비율([ ]%) 실제 수치 산정 기준 마련
- [ ] Rental Filter — 구독/SaaS 형태 계약에 대한 예외 케이스 추가 검토
- [ ] Clause Integrity — `damage` 토픽 외 `termination`/`safety` 교차 오염 규칙 확장
