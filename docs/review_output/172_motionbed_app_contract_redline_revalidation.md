# 172) 모션베드 앱개발 용역계약서 redline 재검증

## 입력/출력
- 원문: `C:\Users\FURSYS\Downloads\모션베드 앱개발 용역계약서_20260416.docx`
- 생성본: `C:\Users\FURSYS\Desktop\aouribot\docs\review_output\aouribot_revision_모션베드_앱개발_20260416.docx`
- 별칭(요청명): `C:\Users\FURSYS\Desktop\aouribot\docs\review_output\aouribot_revision_앱개발계약서.docx`

## 검증 결과 요약 (PASS/FAIL)
- (1) 조/항/호 구조 유지: PASS
- (2) 앱 화면 redline(수정된 부분만): PASS (UI diff 기반 표시)
- (3) Word: 삭제=취소선, 추가=빨간색: PASS
- (4) 고위험만 redline, 중간이하는 blue guidance 분리: PASS
- (5) 오타/어색한 표현 제거(예: “상대방는”, 메타표현): PASS
- (6) 과잉수정 완화(최소 변경): PASS (AI deep review + 최소변경 프롬프트/후처리)

## 핵심 지표(자동 체크)
아래 값은 [revalidate_motionbed_app_contract.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/scripts/revalidate_motionbed_app_contract.py) 실행 결과 기준.

- contract_type: `앱개발/소프트웨어개발/SI/유지보수/SaaS`
- clause_count: `68`
- issue_clause_count: `46`
- display_path 샘플:
  - `제10조 제1항`
  - `제13조 제1항 1호` … `제13조 제1항 5호`
- context_text_count: `42` (상위 조문 컨텍스트가 하위 항목에 동반됨)
- Word redline:
  - 삭제 취소선(`<w:strike>`): `true`
  - guidance 섹션 포함(“권장/참고(guidance)”): `true`
  - 조/항/호 표기 텍스트 포함: `true`
  - 금지 메타 문구 포함(buyer_favorable 등): `false`
  - 조사 오류(“상대방는”): `false`

## AI deep review 적용 범위
- AI enabled/used: `enabled=true, used=true`
- deep review 선택 조항 수: `26`
- 선택 조항 표시는 응답의 `clause_results[].ai_deep_reviewed` 및 `clause_meta.ai.selected_clause_ids`로 확인 가능

## 변경 반영 위치(코드)
- 2단계 구조(스크리닝 → AI deep review), 동적 선택, deep review 표시:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- 세션 리뷰 경로에도 AI/Law 적용(업로드→리뷰 흐름 품질 동기화):
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py#L131-L181)
- Word redline(diff 기반 strike/색상) 출력:
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L102-L136)
