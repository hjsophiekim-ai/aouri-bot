# 156a. 수정 전 테스트 기준선 (2026-11-27)

- 실행: `python -m pytest runtime/tests -p no:cacheprovider` (`__pycache__` 전부 삭제 후, 이 저장소 코드 기준)
- 결과: **22 failed, 1840 passed, 384 subtests passed** (클린 상태에서 3회 실행, 동일)
- 기준 상태: feat/senior-counsel-review-pass + 미커밋 진행 작업 (cross_border 작업 착수 전)

## 선행 문제: traceback 의 Desktop 경로

- `import runtime` 실제 경로는 정상(`C:\aouribot\aouri-bot\runtime`). PYTHONPATH 미설정, editable 설치 없음, conftest 정상.
- 원인: 저장소를 `C:\Users\FURSYS\Desktop\aouribot\` 에서 옮길 때 파일 시각이 보존되어, 옛 위치에서 컴파일된 `.pyc` 505개 중 496개가 유효 캐시로 재사용됨. traceback 에 옛 경로와 `???` 가 찍혔을 뿐 실행 코드는 동일.
- 조치: 모든 `__pycache__` 삭제(생성물, git 무시 대상).

## 실패 목록 (22)

| 테스트 | 메시지(요약) |
|---|---|
| `test_branded_content_golden.PipelineGoldenTest::test_asymmetric_liability_is_legal_core` | KeyError: 'lr_asymmetric_liability' |
| `test_branded_content_golden.PipelineGoldenTest::test_core_findings_and_counts` | AssertionError: Lists differ: [('link_penalty_scope', '제13조', 'MEDIUM'), ('[184 chars]UM')] != [('lr_asymmetri |
| `test_canonical_contract_type_single_source_of_truth.CanonicalContractTypeSingleSourceOfTruthTest::test_all_six_contract_types` | AssertionError: Items in the first set but not the second: '제10조 신설' : [라이선스] UI 노출 HIGH/MEDIUM 조항과 DOCX/PDF 조 |
| `test_canonical_contract_type_single_source_of_truth.UiDocxConsistencyFeedbackTest::test_docx_deduped_clauses_are_marked_suppressed_for_ui` | AssertionError: True is not false : dedup 대표(KR-11)는 숨겨지면 안 된다 |
| `test_construction_contractor_download.ContractorSideRevisionDownloadTest::test_document_carries_contractor_side_clauses` | AssertionError: '검사에 합격한 것으로 본다' not found in "아우리봇 계약 검토·수정본 (법무팀 검토용)\n표시 기준:\n- HIGH / 필수수정: 빨간색\n- MEDIUM  |
| `test_construction_transaction_model::test_지위가_확정되면_파이프라인이_지위별_체크리스트를_주입한다` | AssertionError: assert 'CWP-PAYMENT-PACKAGE' in {'CWC-01', 'CWC-02', 'CWC-07', 'CWC-13', 'clr_late_penalty_rat |
| `test_cross_contract_holdout.CrossContractHoldoutTest::test_every_high_medium_finding_has_a_complete_edit` | AssertionError: Lists differ: ['license/pkg_confidential_ip_boundary'] != []  First list contains 1 additional |
| `test_cross_contract_holdout.CrossContractHoldoutTest::test_pre_performance_recommends_structure_before_wording` | AssertionError: Lists differ: ['barter/pkg_pre_performance_recovery__KR-15-p1: 구조 제안 누락'] != []  First list co |
| `test_cross_contract_holdout.CrossContractHoldoutTest::test_risk_chain_findings_carry_a_complete_edit` | AssertionError: Lists differ: ['license/pkg_confidential_ip_boundary'] != []  First list contains 1 additional |
| `test_fiti_end_to_end_docx.FinalFindingsCollapseReviewFailedTest::test_collapsed_final_findings_is_disclosed_not_silently_served` | AssertionError: '출력 필터가 검토항목 대부분을 제외했습니다' not found in '아우리봇 계약 검토·수정본 (법무팀 검토용)\n표시 기준:\n- HIGH / 필수수정: 빨간색\n |
| `test_freelancer_content_service_golden.PipelineGoldenTest::test_comprehensive_request_is_not_answered_as_adequate` | AssertionError: 0 != 1 |
| `test_hybrid_ai_review.HybridDiscoveryTest::test_ai_discovers_new_risk_with_grounded_quote` | AssertionError: 'LOW' not found in ('HIGH', 'MEDIUM') |
| `test_hybrid_ai_review.FloorProtectionTest::test_ai_cannot_silently_downgrade_layer1_high_finding` | AssertionError: 'LOW' == 'LOW' : clr_payment_guarantee_ambiguous was silently downgraded below its rule-engine |
| `test_macodi_strategic_partnership_regression.DelegatedDesignConstructionServiceGapTest::test_article5_delegated_design_construction_gap_detected` | AssertionError: 'LOW' != 'MEDIUM' - LOW + MEDIUM |
| `test_nda_semantic_scope_regression.NdaSemanticScopeRegressionTest::test_all_golden_issues_are_reviewed` | AssertionError: 'nda_trade_secret_survival_capped' not found in {'nda_improvement_ip_assigned_to_discloser', ' |
| `test_nda_semantic_scope_regression.NdaSemanticScopeRegressionTest::test_no_forbidden_content_production_terms_in_output` | AssertionError: '제14조' unexpectedly found in '{"high_count": 4, "medium_count": 5, "high_issues": [{"clause_id |
| `test_testing_service_contract_regression.PipelineNoOutOfScopeInjectionTest::test_article12_termination_right_vs_2yr_term_is_medium` | AssertionError: 'LOW' != 'MEDIUM' - LOW + MEDIUM |
| `test_testing_service_contract_regression.PipelineNoOutOfScopeInjectionTest::test_article4_4_payment_guarantee_misreading_flagged` | AssertionError: 'LOW' not found in ('HIGH', 'MEDIUM') |
| `test_testing_service_contract_regression.PipelineNoOutOfScopeInjectionTest::test_article6_2_advertising_consent_is_medium` | AssertionError: 'LOW' != 'MEDIUM' - LOW + MEDIUM |
| `test_testing_service_contract_regression.PipelineNoOutOfScopeInjectionTest::test_article8_5_data_reuse_flagged` | AssertionError: 'LOW' not found in ('HIGH', 'MEDIUM') |
| `test_v20_employee_nda_keep_first.GoldenPipelineTest::test_coverage_has_only_requests` | KeyError: 'answered_by' |
| `test_wired_online_supply_golden.PipelineGoldenTest::test_report_coverage_answers_all_four` | AssertionError: Items in the first set but not the second: 'integrity:준거법·관할' : wired_online_supply_draft.txt |
