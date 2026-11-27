# 156. 국제계약(Cross-border) 범용 검토 엔진 — 1단계 원인 분석 및 구현 계획

- 작성일: 2026-11-27
- 기준 계약: 원단 수입 매매 및 품질·대금 정산 계약서(국·영 병기, 한국 구매자 ↔ 이탈리아 공급자, EUR, PI 연동). 이 문서에는 실명·번호를 적지 않는다.
- 분석 자료: 기존 검토 세션(`runtime/data/question_sessions/` 의 해당 세션 JSON — review_result, clause_meta.business_brief), 원문 docx 추출본
- 상태: **계획 승인 대기** — 이 문서 승인 전에는 코드를 수정하지 않는다.

---

## 1. 결론 요약

8개 오류는 "국제계약 로직이 없다"는 한 원인이 아니라, **서로 독립적인 7개의 결함**이 겹친 결과다. 그중 3개(①POS 오탐, ⑤legal map 필드 미전달, ⑦법률명 절단)는 국제계약이 아니어도 모든 계약에 영향을 주는 범용 버그다.

| # | 증상 | 직접 원인(함수·조건) | 성격 |
|---|---|---|---|
| 1 | B2B 수입 매매에 "소비자 대면 판매 … 책임 배분 없음" 최상위 쟁점 | `transaction_structure_signals.py` `_RX_OPERATIVE_SALES_SIGNAL`·`_RX_INTERMEDIATED_SALES_SIGNAL`·`_RX_PAYMENT_CHANNEL_SIGNAL` 의 `POS` 가 `re.IGNORECASE` 로 **영문 "post-arrival", "Purpose", "Disposal"** 에 매치 → "구매자(Buyer)"가 고객 신호, "매매"가 약한 신호로 잡혀 `detect_sales_transaction_ambiguity()` = True → `sales_transaction_rules._apply_missing_consumer_product_liability_check()` 발동. 계약 유형(물품매매) 게이트 없음 | 범용 버그 |
| 2 | 봇이 "계약에 없는 호칭(판매자) — 다른 계약 유형의 문안"이라 판정한 항목이 전달본에 노출 | `redline_integrity.py` `_hold()` 는 수정문만 보류(`integrity_held`)하고 finding 은 살려 둔다. `business_brief.build_business_brief()` L494-500 은 held 항목을 `STATUS_PENDING`("법무 추가 확인 중")으로 바꿔 **hold_reason 을 그대로 사업팀 문장으로 출력**. "다른 계약 유형" 판정을 finding 폐기 신호로 쓰는 경로가 없음 | 게이트 누락 |
| 3 | 존재하지 않는 "제6조 상대방 법인 정보 공란"을 사업부 결정으로 제시 | (a) 세그멘테이션이 **서명란을 제6조 본문에 합침**. (b) `redline_integrity.blank_terms()` 가 체결일 공란 `2026년 11월 [ ]일` 의 뒤 60자 창에 서명란의 "상호 (Company)"가 들어와 `_BLANK_LABELS` 의 `company` → **"상대방 법인 정보"** 로 라벨링. (c) 그 결과가 `commercial_terms` → 전달본 결정사항(L767-778)으로 직행 | 라벨링 오류 |
| 4 | 실제 공란(선적 기한, Incoterms 선택지, 대표자 성명, 체결일) 미탐지 | `blank_terms()` 는 **라벨표에 없는 공란을 버린다**(`if not label … continue`). 선적 기한·Incoterms 라벨이 표에 없음. "서명란"·"단가" 라벨은 명시적으로 제외. **전문(당사자 표)은 조항 목록에 들어가지 않아** `[대표자 성명 입력]` 은 스캔 대상조차 아님. 또 `_RX_BLANK` 가 `[ 3 ]`·`[NR]`·`[CM 79X95 …]` 까지 공란 후보로 보고 라벨 유무로만 거르며, 추출 단계에서 `[      ]` → `[ ]` 로 공백이 접혀 원문 정확 일치 대조가 어긋난다 | 탐지기 한계 |
| 5 | 전문·제1·2조에 명시된 목적·지급 구조를 "확인 필요(추측하지 않음)" 처리 | `clause_level.py` L9958: `(meta["contract_legal_map"]).get("fields")` 로 읽지만 L7924 는 `_legal_map.to_dict()`(**평탄한 dict, "fields" 키 없음**)로 저장 → purpose·payment_flow 가 항상 빈 문자열로 `verification_gate.build_basis()` 에 전달. 보조 경로 `_rx_pay()` 는 "우리/상대방 호칭 + 은/는 … 지급한다" 능동문만 잡아 **"총 계약 금액은 … 지급한다", "shall be paid by T/T" 같은 수동·무주어 지급문**을 놓침 | 범용 버그 |
| 6 | 하자 요청을 제4·5조가 아닌 제3조에 매핑, 수정 문안 없음 | `user_review_request.link_clauses_to_issues()` 의 문서빈도 가중치(`_token_weight`): 조항이 6개뿐이라 "하자·불량·원단"이 절반 초과 조항에 나와 **가중치 0** → 우연한 잔여 토큰으로 제1·3·4·6조 연결(제5조 누락). 이어 `output_filter` dedup 이 제5조 하자 finding 을 "setoff|amend 축" 으로 **제3조에 병합**, `_direct_answer()` 가 `matched[0]`(KR-3)의 경로를 답으로 사용. 주제(하자→품질·검수·클레임·공제) 사전 매핑 없음. 제3조 수정안은 공란을 그대로 둔 원문 복사(`change_record: unchanged`)라 구체 문안이 없음 | 매핑 설계 |
| 7 | "·소비자보호법상" 처럼 잘린 문장 | `statute_grounding.strip_law_mentions()` 가 `_RX_LAW` 목록에 있는 "전자상거래법"만 지우고 목록에 없는 "소비자보호법"은 남겨 **앞 구분자 "·" 가 고아로 남음**(재현 확인). `language_quality_gate` 에 선행 구두점·잘린 법률명 검사 없음 | 범용 버그 |
| 8 | "계약 전에 따로 확인할 사항이 없습니다" | `business_brief.brief_sections()` 3절은 카드의 `checks` + `general_checks` 만 본다. (a) 공란이 확인사항이 아니라 오탐 1건짜리 결정사항으로만 갔고, (b) FTA 원산지·반송비 등 실질 쟁점(counsel_KR-3/5)은 `finance_confirmation` 강등 + Materiality/손실경로 게이트 + dedup 으로 카드에서 빠졌으며, (c) 국제계약 체결 전 필수 확인(준거법·중재기관 확정, Incoterms 선택)을 만드는 룰 자체가 없음 | 복합 |

### 1-1. 추가로 발견한 결함 (사용자 목록 외)

| 코드 | 내용 | 위치 |
|---|---|---|
| A | **방향 역전 수정안**: 제3조에 "공제/상계는 사전 서면합의가 있는 경우에 한한다" 를 추가 제안 — 공제권자는 구매자(우리)인데 우리 공제권을 제한하는 문안. ACT-003 템플릿이 "상대방이 공제하는 계약"만 가정 | ACT-003 addition 템플릿 / `clause_level` addition 경로 |
| B | 요청문의 "하도급사"라는 단어로 하도급법 전략질문(OV-SUB-001~003)과 "부당한 단가 인하" 중점이슈가 주입됨 — 실제 계약은 하도급과 무관한 국제 물품매매 | `user_focus_issues` 키워드 매칭, strategic question 생성 |
| C | 매매계약 하자 근거로 **민법 제667조(도급 담보책임)** 인용 — 매매면 민법 제580조/CISG 제35·38·39조 | consumer rule 의 고정 근거 |
| D | "최종 고객과의 매매계약상 판매자는 누구인가요?" 사전질문 — #1 과 같은 POS 오탐이 `questions/generator.py` L289 에서도 질문을 주입 | `questions/generator.py` |
| E | 국내/국제 판정이 3곳에서 따로 이뤄짐(`jurisdiction.py` = cross_border True, `clause_level._is_domestic_only()` = 외국 표지 하드코딩 목록, `_apply_domestic_filter` 의 LLM 메타). 이번 계약이 "국내 전용"을 피한 것은 **SIAC 명칭 안의 "Singapore" 덕분**(우연). s.r.l./Italy/EUR/IBAN 은 표지 목록에 없음 | 단일 진실 원천 위반 |
| F | 우리 측 호칭이 그룹사 목록(시디즈·알로소 등)으로 채워짐 — 이 계약의 당사자(구매자)는 그룹사가 아닌 협력사. `our_labels` 가 계약 당사자와 일치하지 않아 방향 판정이 흔들림 | entity resolution |

---

## 2. 설계 원칙

1. **판정은 구조 신호로만.** 회사명·품목명·금액·조항번호를 조건문에 쓰지 않는다.
2. **국내/국제 판정은 한 곳.** `jurisdiction.py` 를 확장한 `assess_cross_border()` 하나를 만들고 `_is_domestic_only`·`_apply_domestic_filter`·classifier 가 모두 이 결과를 읽는다.
3. **계약 유형은 기존 canonical 체계에 편입.** 새 유형 코드는 `contract_classifier._classify_type_code()` 가 돌려주고, 룰 계열 게이트(`rule_family_allowed(type_code, family)`)도 같은 표에서 나온다.
4. **evidence_quote 없는 finding 은 출력하지 않는다.** 새 모듈의 모든 finding 은 원문 인용을 갖고, 정규화(공백 접기·따옴표 통일)한 원문에 대한 정확 일치로 검증한다. 공백이 접힌 추출본 문제는 원문 정규화 함수 하나로 양쪽을 같은 규칙으로 맞춰 해결한다(인용 자체를 바꾸지 않음).
5. **국제계약 로직은 신규 패키지로 분리**해 10,000행짜리 `clause_level.py` 에는 호출 지점만 추가한다.

---

## 3. 구현 계획 (2단계)

### 3-1. 신규 모듈 `runtime/review/cross_border/`

| 파일 | 역할 |
|---|---|
| `signals.py` | `assess_cross_border(text) -> CrossBorderAssessment(score, is_cross_border, signals[evidence_quote…], parties_countries, bilingual, prevailing_language)` — 신호군별 가중치(법인 형태 표지 + 비한국 주소, 외국 세무번호, IBAN/SWIFT, 외화+T/T·L/C, Incoterms·B/L·CI·PL·PI·원산지, CISG·중재기관·뉴욕협약, 국·영 병기+언어 우선 조항). **신호군 2개 이상 + 점수 임계치**일 때만 True(단일 신호 판정 금지) |
| `blanks.py` | 범용 공란·미확정 탐지기. 대괄호 안내문(`[대표자 성명 입력]`), 빈 대괄호, `____`, "A / B / C 중 선택", "또는"으로 나열된 미확정 선택지(준거법·중재기관), TBD·to be agreed. 값이 든 대괄호(`[ 3 ]`, `[ 30 ]`)는 **협상 가능한 확정값**으로 분리. 단위 표기(`[ML]`, `[NR]`, `[CM …]`) 제외. 각 항목: 위치(조·항), 원문 인용, 분류(체결 전 필수 확정 / 사업부 결정 / 단순 기재 누락), **의존관계**(예: 선적 기한 공란 → 지체상금 조항 작동 불가). 전문·서명란도 스캔 |
| `bilingual.py` | 국·영 병기 조항을 항 단위로 짝짓기(같은 항 번호 + 국문/영문 판정). 준거법·중재기관·기한 수치·당사자 의무 주체를 양쪽에서 추출해 차이를 보고하고, 언어 우선 조항이 있으면 "우선 언어 기준 결과"를 함께 적는다 |
| `checklist_common.py` | 크로스보더 공통 체크리스트(준거법 확정성·국영 일치·CISG, 분쟁해결 병리조항·seat·규칙·언어·중재인 수·집행, 서류 우선순위, 선급금 보호, 통화·송금·계좌 변경 검증, 세금, 제재(해당 시에만), 책임제한·불가항력·해지·양도·통지·서명권한) |
| `checklist_sale.py` | `international_sale_of_goods` 체크리스트(Incoterms 선택·버전·정합성 — 운임 착불/수출 영세율 문구 ↔ F계열, 위험이전 vs 도착지 검수·적하보험, 선적기한·지체상금 연동·상한 후 구제, 검수·클레임 기간과 잔금 기한 선후, "검수 완료" 정의, 간주 승인, 숨은 하자 배제, 품질 기준 주관성·수치 누락, 구제수단, 수량 오차, 원산지·FTA 추징 부담, 제품 적합성 증빙) |
| `good_clauses.py` | 우리에게 유리하거나 잘 짜인 조항 인정(간주 승인, 서류 우선순위, 계좌 고정, 수량 오차 정산, 반송비 상대방 부담 등) → 법무 내부본 "현행 유지" |
| `evidence.py` | `normalize_for_match()`, `verify_quote(quote, source) -> bool`, `attach_and_verify(findings, text)` — 실패 시 폐기하고 폐기 사유를 내부본에 기록 |
| `redlines.py` | "수정 필요" finding 의 국·영 수정 문안 생성(병기 계약이면 양 언어, 영문 우선이면 영문을 기준 문안으로) — 템플릿 슬롯은 원문에서 뽑은 값으로만 채우고, 정할 수 없는 값은 `[●]` 로 남겨 사업부 결정과 연결 |

모든 체크 항목은 "조항 존재"가 아니라 **확정성·정합성**을 판정하고, 해당 신호가 없으면 아무 것도 만들지 않는다(예: 제재는 품목·국가 신호가 있을 때만).

### 3-2. 계약 유형 확장 (`contract_classifier.py`, `canonical_transaction_facts.py`)

- 신규 코드: `international_sale_of_goods`, `international_distribution`, `international_license`, `international_services`, `international_nda`, `international_mou_jv`.
- `_classify_type_code()` 앞단에서 `assess_cross_border()` 가 True 이면 국내 유형 판정 결과를 국제 계열로 **매핑**(purchase_supply → international_sale_of_goods, distribution_resale/dealer_agency → international_distribution, nda_confidentiality → international_nda …). 국내 유형 판정 로직은 복제하지 않는다.
- `rule_family_allowed(type_code, family)` 표 신설 — `consumer_sales`, `dealer_rental(DLR)`, `consignment(시디즈 위탁 전략 포함)`, `subcontract(하도급)`, `privacy` 계열은 국제 계열 유형에서 기본 차단. 기존 국내 유형의 동작은 그대로.

### 3-3. 기존 코드 수정 (원인별)

| 원인 | 수정 |
|---|---|
| #1, D | `transaction_structure_signals.py`: `POS` 를 `\bPOS\b`(대소문자 구분) + "포스 단말" 로 한정. `_RX_CUSTOMER_SIGNAL` 의 "구매자"는 당사자 정의어("구매자(이하 갑)")일 때 고객 신호에서 제외. `sales_transaction_rules._apply_missing_consumer_product_liability_check()` 에 **소비자 직접 신호 게이트**(소비자·최종소비자·고객 응대·청약철회·전자상거래·B2C·통신판매) 필수 + `rule_family_allowed(type, "consumer_sales")`. 근거 조문을 계약 성격별로(매매면 민법 제580조) — 고정 민법 제667조 제거 |
| #2 | `final_findings_builder`/`output_filter` 단계에 **유형 불일치 폐기 게이트**: `integrity_held` 사유가 "다른 계약 유형의 문안"·"계약에 없는 당사자 호칭"이면 finding 을 `excluded_from_brief=True` 로 바꾸고 `internal_only_reason` 을 남김. `business_brief` 는 이 표지 항목을 카드·요청답변·결론에서 제외하고, 법무 내부본에만 사유와 함께 남김 |
| #3, #4 | `redline_integrity.blank_terms()` 를 `cross_border/blanks.py`(범용, 국내 계약에도 적용) 결과로 대체: 라벨이 없더라도 공란은 버리지 않고 "주변 조항 제목·항 제목"으로 라벨링, 라벨 창은 **같은 문장/항 안으로 제한**(서명란의 "Company" 가 체결일 공란 라벨이 되지 않게), 서명란·전문을 별도 영역으로 분리해 "대표자 성명·체결일 = 단순 기재 누락"으로 분류. 세그멘테이션은 건드리지 않고(회귀 위험) 공란 탐지기에서 서명란 경계를 인식 |
| #5 | `clause_level.py` L9958: `contract_legal_map` 저장 형태(평탄 dict)에 맞게 읽도록 수정(`fields` 가 있으면 그것, 없으면 dict 자체). `verification_gate._rx_pay()` 에 무주어·수동 지급문(“…은 … 지급한다”, “shall be paid/remitted”)을 계약 전체 지급 구조로 인식하는 보조 패턴 추가. 추가로 `cross_border` 의 거래 사실 추출(전문·목적·품목표·대금 조항)을 `basis_fields` 의 fallback 으로 사용 |
| #6 | `user_review_request` 에 **주제 사전**(하자 → 품질·검수·클레임·공제·반송, 세금 → Incoterms·원산지·부가세·관세·원천징수, 대금 → 지급·선급·잔금·송금·계좌) 추가 — 조항 제목·본문 표지로 먼저 연결하고, 기존 토큰 가중치는 보조로. 요청 답변 경로는 dedup 병합 전 원 finding 위치를 유지(`origin_display_path`). "수정 필요" 판정에는 국·영 수정 문안이 반드시 붙도록 `requested_clause_review` 에서 검사 |
| #7 | `strip_law_mentions()` 가 법률명 나열("A·B법상")을 **통째로** 지우거나, 지울 수 없으면 원문 유지. `language_quality_gate` 에 "문장·구절 머리 고아 구두점(·, ,, /)", "법(상|의) 앞 2자 미만 잘림", 괄호 짝 불일치 검사 추가 → 위반 문장은 전달본에서 원문 문장으로 복구하거나 제외 |
| #8 | 크로스보더 체크리스트의 "체결 전 필수 확정" 항목과 공란 탐지 결과를 `business_brief` 의 `general_checks`/카드 checks 로 공급. `finance_confirmation` 으로 강등된 항목도 "재경 확인" 행으로 3절에 남김(사라지지 않게). 3절이 비었는데 HIGH/MEDIUM 카드가 있으면 "확인사항 없음" 문구 대신 내부 일관성 오류로 처리 |
| A | ACT-003 addition 템플릿에 공제권자 판정 추가 — 공제·상계권자가 우리 측이면 "공제 제한" 문안을 내지 않고 반대로 "공제 근거·증빙 절차" 문안을 냄 |
| B | `user_focus_issues` 의 "하도급" 계열은 계약 본문에 하도급 표지가 있을 때만 활성(요청문의 당사자 소개 문구만으로 활성화 금지). 전략질문 OV-SUB 계열도 `rule_family_allowed` 게이트 |
| E | `_is_domestic_only()` 와 `_apply_domestic_filter()` 가 `assess_cross_border()` 결과를 읽도록 교체(하드코딩 표지 목록 제거) |

### 3-4. 거래 사실 추출 보강

`cross_border/facts.py`(또는 `contract_overview.py` 확장): 전문·목적 조항·품목표·대금 조항에서 거래 목적, 당사자별 지위(당사자 표의 "구매자 (Buyer)" 등 명시 지위 = 확정), 지급 주체·금액·방식(T/T, 선급/잔금 비율)을 추출. 실패한 필드만 "확인 필요". 우리 회사가 어느 쪽인지 원문으로 확정되지 않으면 `runtime/questions/` 사전질문으로 묻고 추측하지 않는다.

### 3-5. 출력 경로

- 사업팀 전달본: 국제계약 공통/유형 체크리스트 결과를 기존 카드 구조(위험도·조치 유형·수정 전/후)로. 공란은 분류에 따라 "체결 전 필수 확정"(카드+3절) / "사업부 결정"(4절) / "기재 누락"(3절 한 줄).
- 법무 내부본: 폐기된 finding(사유 포함), 현행 유지 조항과 근거, 국·영 대조표, 증거 인용 검증 결과.

---

## 4. 테스트 계획 (3단계)

- 러너: pytest 9 + `unittest.TestCase` 스타일(기존 111개 중 105개가 TestCase). conftest 가 AI 키를 제거하므로 결정론적 경로로 검증한다.
- `runtime/tests/fixtures/intl_sale_goods_fabric_anon.txt`: 기준 계약 **비식별본** — 회사명·사업자번호·VAT·주소·IBAN·BIC·PI 번호를 가상값으로 교체, 조항 문언·공란(공백 폭 포함)·국영 불일치는 그대로.
- `runtime/tests/test_international_sale_of_goods_regression.py`: 사용자 지정 MUST/MUST NOT 표 전부를 개별 테스트로. 엔진 단위(체크리스트·공란·게이트)와 전달본 단위(`build_business_brief` 결과 문자열) 두 층으로 검증.
- 범용 fixture 3종(직접 작성): ① 미국 독점 판매점(영문 단일, 뉴욕주법, 뉴욕 법원 전속관할) ② 중국 OEM 공급(국·영 병기, CIETAC, DDP, 선급 30%) ③ 유럽 상표 라이선스(로열티 원천징수, 준거법 미기재) — 각각 공통 체크리스트 기대 결과 + 국내 전용 룰 미발동 확인.
- 범용 버그(#1·#5·#7) 단위 테스트: "Purpose/post-arrival" 문장이 판매 신호가 되지 않음, legal map 평탄 dict 전달, "A·B법상" 절단 금지.
- 전체 회귀: 기존 스위트 전부. 기대값 변경이 필요하면 보고서에 사유 명시(특히 #5 수정으로 기존 계약들의 "확인 필요" 문구가 사라지는 테스트가 있을 수 있음).

## 5. 결과 보고 (4단계)

비식별 fixture 로 전달본·내부본 재생성(AI 없이 결정론 경로) → `docs/review_output/157_…` 에 수정 전·후 비교, 변경 파일·함수, MUST/MUST NOT 충족표, 범용 fixture 결과, 남은 한계.

---

## 6. 승인 시 확인이 필요한 사항

1. **검토 관점** — 기준 계약의 "우리"는 구매자(그룹 외 협력사)로 본다. 기존 세션은 우리 호칭을 그룹사 목록으로 채웠다(결함 F). 그룹사가 아닌 당사자를 위해 검토할 때 관점을 어떻게 정할지: 원문 당사자 표의 지위 + 사용자 요청문으로 정하고, 둘이 충돌하면 사전질문으로 묻는 방식을 제안한다.
2. **Incoterms 권고** — 사용자 사전답변은 "FOB". MUST 표는 "FCA 계열 권고"다. 엔진 결론은 "미선택 = HIGH, 운임 착불·수출 영세율 문구와 정합하는 것은 F계열(FCA/FOB), CIF 는 충돌. 출발지가 내륙이면 FCA [지정장소]가 실무상 자연스럽고, FOB 를 택하면 선적항을 지정해야 하며 그 항구까지의 내륙운송은 공급자 부담"으로 낸다. 답변값(FOB)은 "상대방 합의 전 제안값"으로만 표시한다(기존 원칙과 동일).
3. **공란의 등급** — 현재 전달본은 "공란 자체는 위험 등급 근거가 아니다"(LOW 고정, `business_brief` L778) 원칙이다. 이번 요구(선적 기한·Incoterms 공란 = HIGH)와 맞추기 위해 **다른 조항의 작동을 막는 공란(의존관계 있음)과 필수 거래조건 공란만 HIGH**, 그 밖의 공란은 기존처럼 LOW/결정사항으로 두는 규칙을 제안한다.
4. **범위** — #5(legal map 필드 미전달)·#7(법률명 절단)·POS 오탐 수정은 국내 계약 출력도 바꾼다. 의도된 개선이지만 기존 테스트 기대값 일부가 바뀔 수 있다.
5. **재생성 방식** — 4단계 재생성은 비식별 fixture + AI 미사용 경로로 한다. 실제 원본으로 AI 포함 재검토가 필요하면 별도로 실행한다(원문이 AI 공급자로 전송됨).
