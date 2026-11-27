# 157. 국제계약(Cross-border) 범용 검토 엔진 — 결과 보고 (수정 전·후 비교)

- 작성일: 2026-11-27
- 브랜치: `feat/cross-border-review` (push 하지 않음)
- 커밋
  1. `3dfaed5` chore: senior counsel review pass 진행 작업 반영 (기존 미커밋 작업 고정, 알려진 실패 22건 — 156a)
  2. `358834a` fix(review): 범용 버그 수정 (#1·#2·#3·#4·#5·#6·#7, 방향 게이트, 법률 질문 게이트, 그룹사 호칭)
  3. `93e5347` feat(review): cross_border 패키지
  4. (이 보고서 커밋) test/docs: 회귀 테스트·비식별 fixture·보고서·재생성본
- 관련 문서: 156(원인 분석·계획), 156a(수정 전 테스트 기준선), `157_regenerated/`(재생성본)

---

## 1. 요약

| 구분 | 수정 전(기존 세션 결과) | 수정 후(비식별 fixture, AI 없이 재생성) |
|---|---|---|
| 판단 | 조건부 진행 가능 — "사업부 결정 1건"(가짜 공란) | 조건부 진행 가능 — 핵심 수정 2건·중요 확인 1건·사업부 결정 2건 |
| 최상위 쟁점 | 소비자 대면 판매 책임 배분(오탐) | 인도 조건(Incoterms) 미선택(HIGH), 중재기관 선택형·중재지 미지정(HIGH), 선적 기한 공란(HIGH) |
| 쟁점 수 | 2건(소비자 판매, 가짜 '상대방 법인 정보') | 14건(HIGH 3 · MEDIUM 6 · LOW 5, 사업부 결정 2 포함) |
| 계약 전 확인사항 | "없음" | 9건(인도 조건·선적항, 적하보험, 중재기관, 선적 기한, 원산지, 계좌 확인 등) |
| 요청 매핑 | 하자 → 제3조, 세금 → 제3조(근거 없음) | 하자 → 제4조·제5조(+잔금 기한), 세금 → 제3조 제2항(Incoterms·원산지), 대금 → 제2조·제3조·제5조 |
| 수정 문안 | 구체 문안 없음 | 수정 필요 항목 전부 국·영 구체 문안(영문 우선 조항 고려) |
| 근거 조문 | 민법 제667조(도급) | CISG 제35·38·39·46·49·50·74·81조, 관세법 특례법, 민사소송법 제217조, 뉴욕협약 |

## 2. 원인 → 변경 (함수 단위)

| # | 원인(156) | 변경 파일·함수 |
|---|---|---|
| 1 | `POS` 대소문자 무시 매치(post-arrival·Purpose·Disposal), 당사자 정의어 "구매자"를 고객 신호로 | `transaction_structure_signals.py`: `_RX_OPERATIVE/INTERMEDIATED/PAYMENT_CHANNEL_SIGNAL`(대문자 `\bPOS\b`), `_RX_BUYER_AS_PARTY`, `has_direct_consumer_signal()` · `sales_transaction_rules._apply_missing_consumer_product_liability_check()`(직접 소비자 신호 필수) · `cross_border/types.rule_family_allowed()` + `engine.gate_rule_families()` |
| 2 | 보류 사유를 그대로 전달본에 노출 | `redline_integrity.exclude_from_brief()`·`check_finding()` · `business_brief.build_business_brief()`(excluded_from_brief 제외) |
| 3 | 서명란이 제6조에 붙어 체결일 공란 뒤 "Company"가 라벨 | `redline_integrity.blank_terms()`(같은 줄 문맥, 서명란·전문 기재사항 분리) · `cross_border/blanks.py` |
| 4 | 라벨 없는 공란 폐기, 전문 미스캔 | 같은 함수 — 항 머리 라벨, 라벨표(선적 기한·인도 조건) 추가, 전문 스캔, 값 든 괄호·단위 제외 |
| 5 | `contract_legal_map` 을 `.get("fields")` 로 읽음 | `clause_level.py` 필수 검증 basis_fields · `verification_gate.build_basis()`(수동형 지급문 `_RX_PASSIVE_PAY`) |
| 6 | 빈도 가중치 0 → 잔여 낱말로 조항 연결 | `user_review_request.topic_clause_links()`·`REQUEST_TOPICS`·`link_clauses_to_issues()` · `cross_border/engine.overlay_requests()` |
| 7 | 법률명 목록 일부만 삭제 → "·소비자보호법상" | `statute_grounding.strip_law_mentions()` · `language_quality_gate.orphan_separator_spans()/repair_orphan_separators()`·검사 (c) · `business_brief._clean()` |
| 8 | 확인사항 공급 경로 없음 | cross_border finding 의 `brief_checks`·`action_only`, `delivery_docs.brief_from_meta()`(LOW 국제 항목) |
| A | 우리 공제권을 묶는 정산 템플릿 | 신규 `direction_gate.py`(`apply_direction_gate`, `check_added_text`) — `clause_level`(생성 단계)·`redline_integrity.run`(무결성 단계) |
| B | 요청문 "하도급사"로 하도급법 질문 | `strategic_inquiry.generate_strategic_inquiry(contract_text=)`(구조 신호 `structure`) · `user_focus.parse_user_focus_issues(contract_text=)`(`_STATUTE_GATED_KEYWORDS`) |
| C | 매매 하자에 민법 제667조 | `statute_grounding.detect_relations(cisg=)`·CISG 조문 · `senior_counsel_audit`(`cisg_applies`) |
| E | 국내/국제 판정 3곳 | `cross_border/signals.assess_cross_border()` 하나로 — `_is_domestic_only`, `canonical_state.build_canonical_state(contract_text=)` |
| F | 그룹사 목록을 기본값으로 우리 호칭에 | `group_entities.our_side_labels()`(그룹사가 계약 당사자일 때만) · `cross_border/perspective.py`(당사자 표 + 요청문, 충돌 시 사전질문) |

## 3. MUST / MUST NOT 충족

시험: `runtime/tests/test_international_sale_of_goods_regression.py`(33건, 엔진·전체 파이프라인·범용 결함 3층).

| MUST | 결과 | 등급·분류 | 시험 |
|---|---|---|---|
| 제3조 제1항 선적 기한 공란 → 제3조 제3항 지체상금 작동 불가 | 충족 | HIGH / 체결 전 확인(필수 확정) | `test_shipment_deadline_blank_disables_liquidated_damages` |
| 제3조 제2항 Incoterms 미선택, ASSEGNATO·영세율 ↔ F조건, 적하보험 | 충족 | HIGH / 필수수정 | `test_incoterms_unselected_with_proposed_fob`, `..._recommends_fca` |
| 제6조 제2항 준거법 국문("또는 중립국 법")·영문 불일치 | 충족 | MEDIUM(영문 우선이라 확정 쪽) | `test_governing_law_mismatch` |
| 제6조 제2항 중재기관 선택형·중재지 미지정 | 충족 | HIGH | `test_arbitration_institution_alternative_and_no_seat` |
| 선급금 반환·해제권 부재, 지체상금 상한 후 구제수단 부재 | 충족 | MEDIUM | `test_advance_refund_and_post_cap_remedy` |
| 잔금 기한(14일) ↔ 클레임 기한(30일), 검수 완료 정의 부재 | 충족 | MEDIUM | `test_balance_due_before_claim_period` |
| 재단·가공 전 하자 한정 → 숨은 하자 배제 | 충족 | MEDIUM | `test_latent_defects_excluded` |
| 원산지 부적격 시 관세 추징 부담 주체 | 충족 | MEDIUM | `test_origin_duty_liability` |
| 색상 편차 주관성·치수 허용 오차 수치 누락 | 충족 | LOW | `test_low_items` |
| PFC FREE 적합성 증빙 | 충족 | LOW | `test_low_items` |
| 송금 계좌 변경 검증 절차 | 충족 | LOW | `test_low_items` |
| 대표자 성명·체결일 공란 | 충족 | 사업부 결정 | `test_blanks_and_negotiable_values`, `test_must_cards` |
| 요청(하자) → 제4조·제5조, 요청(세금) → 제3조 제2항 | 충족 | — | `test_request_mapping` |

| MUST NOT | 결과 | 시험 |
|---|---|---|
| 소비자 대면 판매·배송·환불·진위·IP 책임 배분 | 없음 | `test_must_not`, `test_pos_is_not_matched_inside_english_words` |
| 렌탈·딜러·위탁판매·개인정보 | 없음 | `test_must_not` |
| "제6조 상대방 법인 정보 공란" | 없음 | `test_blank_terms_has_no_phantom_counterparty_info`, `test_must_not` |
| 거래 목적·지급 구조 "확인 필요(추측하지 않음)" | 없음(needs_confirmation = []) | `test_verification_passes_with_confirmed_perspective` |
| "계약 전 확인사항 없음" | 없음(9건) | `test_pre_signing_checks_present` |
| 원문에 없는 인용 | 없음(정확 일치 검증, 폐기 0건) | `test_every_finding_quote_is_in_the_contract`, `test_every_live_finding_quote_exists` |
| 잘린 법률명 등 문장 품질 위반 | 없음 | `test_language_quality`, `test_law_name_not_truncated` |

## 4. 범용 fixture 결과 (`test_cross_border_generic.py`, 9건)

| fixture(가상) | 국제 유형·관점 | 나온 지적 | 나오지 않아야 할 것(확인됨) |
|---|---|---|---|
| 미국 독점 판매점(영문 단일, 뉴욕주법, 뉴욕 법원 전속관할) | international_distribution · 판매점 | 외국 법원 전속관할(MEDIUM, Article 7.2), 계약서↔PO 우선순위(LOW) | 준거법 지적 없음(뉴욕주법 확정), 불가항력 지적 없음, 대리점법·렌탈 등 국내 룰 없음 |
| 중국 OEM(국·영, CIETAC·상하이·3인·영어, DDP, 선급 30%) | international_sale_of_goods · 구매자 | 선급금 반환·해제권 없음(MEDIUM), CISG 자동 적용 정리(LOW) | 중재조항 오탐 없음, Incoterms 미선택 없음(DDP), 구제수단 지적 없음(교체 의무 있음) |
| 유럽 상표 라이선스(로열티, 준거법 미기재, ICC·파리) | international_license · 라이선시 | 준거법 미지정(HIGH), 원천징수 조항 없음(MEDIUM, 법인세법 제98조) | 중재조항 오탐 없음, 분쟁해결 부재 오탐 없음 |

세 계약 모두 전체 파이프라인을 AI 없이 돌려 사업팀 전달본에 소비자 대면·전자상거래법·렌탈·위탁판매·하도급법·대리점법 문구가 없음을 확인했다.

## 5. 테스트 결과

| 시점 | runtime/tests 결과 |
|---|---|
| 수정 전 기준선(156a) | 22 failed, 1840 passed |
| 최종(이 보고서 시점) | **22 failed, 1882 passed, skipped 0** — 실패 22건은 기준선과 같은 테스트(새 실패 0, 고친 것 0). 통과 +42 는 새 테스트 |

- 기존 실패 22건은 이번 작업에서 고치지 않았다(지시대로 별도 작업).
- **skip**: 실데이터 fixture 가 있는 이 PC 에서는 0건. 저장소만 받은 환경(실데이터 폴더 없음)을 흉내 낸 실행에서는 실데이터를 쓰는
  시험이 사유 메시지("실데이터 fixture 없음: … AOURIBOT_PRIVATE_FIXTURES 폴더에 두면 실행됩니다")와 함께 건너뛴다 — 해당 10개 파일
  기준 85 passed, 34 skipped(그중 `test_deal_flow_caixi.py` 는 파일 자체가 커밋 제외).
- 실행 중 소스를 고쳐 생긴 지문 시험 실패 1건, 부하로 인한 서버 연결 끊김 1건은 단독 재실행에서 통과했다(최종 전체 실행에서는 둘 다 통과).
- `tests/test_nda_review.py`(상위 tests 폴더, 같은 파일명 충돌로 별도 실행): 5 passed, 2 skipped(기존 조건부 skip).

### 기존 테스트 기대값 변경

**기대값(판정·등급·개수)을 바꾼 기존 테스트는 없다.** 기존 테스트 파일을 고친 것은 다음 두 종류뿐이다 — 판정 기준을 느슨하게 한 것이 아니다.

| 파일 | 변경 | 사유 |
|---|---|---|
| `test_privacy_term_linkage.py`, `test_redline_integrity.py`, `test_deal_flow_caixi.py`(커밋 제외) | 실데이터 fixture 를 저장소 밖 폴더에서 읽고, 없을 때만 사유와 함께 skip | 실데이터 비공개(커밋 1) |
| `test_privacy_term_linkage.py` | 시험 문장의 실제 업체명 "현대벤디스 식권대장" → "한결식권 식사관리" | 실명 제거 |
| `test_change_set_tracked_compare.py`, `test_deal_scenarios.py`, `test_ndg_clause_linkage_and_tracked_changes.py`(파일명 변경), `test_scenario_gate.py`, `test_verification_gate.py`, `test_verification_output_control.py`, `runtime/tests/test_nda_review.py`, `tests/test_nda_review.py` | 실제 거래 상대방 약칭·회사명·주소(PDG / Porsche / 실주소)를 가상값(NDG / Norden / Musterstraße 1, 5020 Salzburg)으로 | 실명 제거 — 기대값의 의미는 그대로(이름만 바뀜) |

## 6. 실명 교체 위치(커밋 1)

| 대상 | 교체 | 위치 |
|---|---|---|
| PDG → NDG, Porsche → Norden, 포르쉐 → 노르덴, Porschestrasse 1, 70435 → Nordenstrasse 1, 70000 | 코드 주석·정규식·시험 문장 | runtime/review: clause_extraction, clause_index, clause_label, clause_level, commercial_request_review, deal_scenarios, docx_splice, effect_baseline_review, entity_resolution, priority_map, requested_clause_review, review_isolation, revision_set_check, senior_counsel_audit, source_docx, text_extract, user_request_answers, verification_gate · runtime/tests: change_set_tracked_compare, deal_scenarios, ndg_clause_linkage_and_tracked_changes, scenario_gate, verification_gate, verification_output_control, nda_review · tests/test_nda_review · scripts/verification_gate_cases |
| `requested_clause_review` 의 상대방 약칭 하드코딩(정규식 `상대방|PDG|…`) | 약칭 고정 대신 대문자 약칭 2~6자로 일반화, 확인 문구는 "상대방과 확인" | 과적합 제거 |
| Flugplatzstraße 29, 5700 Zell am See(실주소) | Musterstraße 1, 5020 Salzburg | runtime/tests/test_ndg_…, tests/test_nda_review |
| 현대벤디스 식권대장 | 한결식권 식사관리 | runtime/tests/test_privacy_term_linkage |
| 실명이 필요한 실데이터 전용 스크립트 5종(make_pdg_variant, check_pdg_acceptance, run_pdg_case, run_final_set, run_verification_offline_set) | 커밋 제외(.gitignore) — 로컬에서만 원본 그대로 동작 | 실데이터 매핑표가 실명을 담아야 함 |

- 이미 커밋된 과거 이력(HEAD 이전의 clause_level.py·tests/test_nda_review.py 의 "PDG"·"Porsche")은 이력 재작성을 하지 않았다 — 필요하면 별도 결정.
- 바깥 저장소(`C:\aouribot`)의 `aouri-bot_claude_code_prompt.md`, `docs/aouri-bot_claude_code_prompt.md`, `run_aouri_upgrade.sh`, `docs/run_aouri_upgrade.sh` 에도 "PDG/Porsche" 가 있다 — 이번 작업 범위(aouri-bot 저장소) 밖이라 손대지 않았다.

## 7. 비공개 자료 처리

- 원본 docx(`Downloads\Fabric_Quality_Assurance_and_Payment_Deduction_Agreement-v6.docx`)는 저장소에 복사하지 않았다. 저장소의 기준 계약은 비식별 텍스트 fixture 뿐이다.
- 실데이터 fixture 는 `C:\Users\FURSYS\aouribot-private-fixtures`(저장소 밖, `AOURIBOT_PRIVATE_FIXTURES` 로 변경 가능).
- `.gitignore`(aouri-bot): `reports_evidence/`, 실데이터 fixture 옛 경로, 실명 포함 시험·스크립트 7종. `git check-ignore` 로 확인.
- 기존 검토 세션(`runtime/data/question_sessions/…`)은 원래부터 `.gitignore` 대상.

## 8. 남은 한계와 사람 판단이 필요한 부분

1. **유형별 체크리스트는 국제 매매만 상세하다.** 판매점(최소구매량 미달 효과·독점 해지·종료 후 재고), 라이선스(품질관리·표장 사용 기준·
   종료 후 재고 처분), 용역(고정사업장·산출물 귀속), MOU(구속력 범위) 전용 항목은 아직 공통 체크리스트(준거법·분쟁·원천징수 등)만 돈다.
2. **결정론 경로 기준 검증이다.** AI(계약 맵·사내변호사 에이전트) 켜진 운영 경로에서는 AI finding 이 함께 나온다 — 그 finding 도 방향 게이트·
   유형 게이트·인용 검증·문장 품질 게이트를 거치지만, 실제 원본으로 AI 포함 재검토는 하지 않았다(원문이 AI 공급자로 전송됨 — 사용자 결정 사항).
3. **신호 사전의 범위.** 국가·주(州)·법인 형태·중재기관 사전에 없는 표기(예: 드문 국가의 법인 형태)는 놓칠 수 있다 — 단일 신호로는 판정하지 않으므로
   오탐보다 미탐 쪽으로 치우친다.
4. **국·영 의미 대조는 준거법·중재 등 핵심 조항 중심이다.** 모든 항의 의미 차이를 찾지는 않는다(예: 제4조 제2항 국문 "재단·가공 전 상태에서 발견된
   하자"와 영문 "not been cut or processed"의 미묘한 차이는 숨은 하자 항목에서 함께 다룰 뿐 별도 지적하지 않는다).
5. **사람 판단이 필요한 값.** `[  ]` 로 남긴 수정 문안의 값(숨은 하자 통지 기간·클레임 기간, 해제 유예 일수·반환 기한, 그레이스케일 등급·ΔE·치수
   허용 오차, 교체품 재선적 기한)은 사업부·법무가 정한다. 인도 조건은 사용자 답변 FOB 를 "합의 전 제안값"으로만 반영했고 선적항은 공란이다.
6. **CISG 체약국 목록**은 주요국만 담았다 — 목록 밖 국가는 "확인 필요"로 둔다.
7. **근로관계 계약은 국제 체크리스트 대상에서 뺐다**(근로자 서약 전용 엔진이 본다).

## 9. 재생성본 (`docs/review_output/157_regenerated/`)

- `brief_사업팀전달본.docx` / `.md` — 사업팀 전달본
- `legal_법무내부분석본.docx` / `_텍스트.md` — 법무 내부 분석본(현행 유지 판단 7건 포함: 서류 간 우선순위, 검수 결과 승인 간주, 수량 허용 오차 정산,
  반송 비용 공급자 부담, 지급 계좌 특정, 수출 통관·영세율 협조 구조, 정산 기준)
- 모두 비식별 fixture 로 AI 없이 만든 것이다.
