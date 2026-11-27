# 158. 사업팀 전달본 정리 · 표 셀 레드라인 수정 — 원단 수입 계약 재검토 후속

- 작성일: 2026-11-27
- 브랜치: `feat/cross-border-review`
- 계기: 앱에서 원단 수입 계약(국·영 좌우 병기 표)을 다시 검토한 결과 — 법률 판단은 좋아졌으나 사업팀 전달본을 보낼 수 없는 상태

## 1. 수정 전·후 비교 (같은 원본 docx)

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 변경추적본 삽입·삭제 | 삽입 8 · 삭제 0 (사용자 실측) | **삽입 43 · 삭제 15** |
| 수정안 변경추적본 반영 | 다수 "제안만 있음·파일 미반영" | **23건 전부 반영(미반영 0)** |
| 사업팀 전달본 쪽수(PDF) | **10쪽** | **3쪽** |
| 판단 | 검증 미통과 초안 — 최종본·서명 가능 판정 불가 | 조건부 진행 가능(체결 전 필수 확정 5건, 핵심 수정 2건) |
| 당사자 지도·관점 | 우리 당사자 미확정 | 구매자(갑) 확정 — 당사자 표 지위 + 요청문 |
| 수정안 무결성 검사 | `'str' object has no attribute 'get'` 오류 | 정상 |
| 대표자 성명·체결일 | 누락 | 사업부 결정(기재 누락)으로 표시 |

측정 방법
- 수정 후: 세션에 저장된 원본 docx·요청문·사전 답변으로 이 브랜치 코드를 AI 없이 다시 돌려 변경추적본과 전달본 PDF를 만들었다.
- 수정 전 쪽수: 수정 전 커밋(`04aacbc`)을 임시 작업 폴더로 꺼내, 같은 세션에 저장된 이전 검토 결과로 전달본 PDF를 만들었다.
- 쪽수는 앱의 전달본 PDF 생성기(fpdf, A4) 기준이다. Word(DOCX) 쪽수는 Word 렌더링이 필요해 재지 못했다.
- 앱(AI 포함) 경로로 다시 생성하지는 않았다(원문이 AI 공급자로 전송됨 — 사용자 결정 사항).

## 2. 원인과 변경

| 지적 | 원인 | 변경 |
|---|---|---|
| 표 셀 치환 전부 실패 | `docx_redline` 이 본문 직계 단락만 수집(`[el for el in body if el.tag == p]`) — 표 셀 안 단락이 후보에서 빠짐. 삽입은 `body.insert` 로 셀 밖에 들어감 | `_doc_paras()`(문서 전체 단락), `_insert_after_el()`(기준 단락의 부모=셀 안에 삽입) |
| 조 범위가 틀어짐(제4조가 제2조 단락에서 시작) | `_build_article_index` 가 본문 속 인용("제4조의 입고 검수", "under Article 4")과 항 번호("1. …")를 조 머리로 셈 | 단락 첫머리의 "제N조 / Article N" 머리가 2개 이상이면 그것만 사용(머리가 없는 문서는 종전 방식) |
| 같은 단락의 두 번째 수정 실패 | 여러 run 에 걸친 문장은 이미 수정된 단락에서 치환 불가 | `_substitute_across_runs()` — 삭제·삽입 표시가 없는 연속 run 구간 안에서만 잘라 치환(줄바꿈·탭이 끼면 포기) |
| 신설 항이 엉뚱한 조 끝(제5조 제1항 뒤)에 | 좌우 병기 표에서 '조의 끝'이 다른 셀·다른 조로 잡힘 | cross_border 신설 수정에 기준 단락(`anchor_text` — 그 항의 언어별 마지막 줄)을 주고 그 바로 뒤(같은 셀)에 삽입 |
| 우리 당사자 미확정 | 관점 판단에 사전질문 문구까지 섞여 "구입" 요청이 충돌로 판정. 거래 흐름 단계는 표 안 당사자 칸을 읽지 못함 | `perspective.user_words()` — 요청 본문 + 답변 값만. 확정 관점을 거래 흐름(`run_deal_flow_stage(known_role=)`)·필수 검증이 그대로 사용 |
| `'str' object has no attribute 'get'` | cross_border finding 의 `loss_path` 가 문자열 — `executive_summary` 는 dict 로 읽음. 이 예외로 무결성 결과가 통째로 오류로 덮여 요청 매핑·공란 결정사항이 사라짐 | 표준 구조 `{"event","failed_protection","loss"}` 로 |
| 전달본의 도구 상태 문구 | 검증·적용 상태를 전달본 본문에 씀 | 전달본에서 제거(법무 화면 배너·법무 내부 분석본에만). `output_consistency` 에 "전달본에 도구 상태 문구 없음" 검사(`RX_TOOL_STATUS`) 추가 |
| 도구 실패가 결론을 바꿈 | 보류·검증 미통과가 판단을 "진행 보류"·"검증 미통과 초안"으로 덮음 | 결론은 계약 리스크로만. 반영 실패·검증 미해결이 있으면 `delivery_blocked` — 전달본 다운로드를 409로 거부하고 법무 화면에만 사유 표시 |
| 수정 전/후 블록, 영문 수정안 | 종전 형식 | 국문 변경 표시 한 블록만(바뀌지 않은 앞뒤는 30자만 남기고 "…"), 항 신설은 추가 문장만, 영문은 변경추적본에만 |
| 미확정 조건이 문장 조각 | `undecided_terms` 가 앞뒤 글자를 잘라 씀 | cross_border 수정에 항목 이름표(`UNDECIDED_LABELS`: "선적 기한(주)", "숨은 하자 클레임 기간(개월)" …), 그 밖의 수정은 낱말 경계로 |
| 등급·분류 불일치 | — | 필수수정은 MEDIUM 이상으로 맞춤. 중재기관 선택형 HIGH, 선급금 반환·해제권 MEDIUM 유지 |
| 같은 주제 요청 모순(반영 / 부분 반영) | 요청 ↔ 쟁점 연결이 위 예외로 실행되지 않음 | 예외 해결 + 같은 답을 받은 요청은 한 줄로 합침 |
| 전달본 형식 | — | 1) 결론 한 문단 + 요청 → 쟁점 번호 2) 체결 전 필수 확정 사항(Incoterms·선적 기한·공란·선택형 조항·기재 누락) 3) 쟁점별 요약(현재·위험·조치 1~2문장 + 국문 변경 표시) 4) 계약 전 확인사항 5) 파일 안내 한 줄. 국제계약은 거래 흐름 절(0-x)을 넣지 않음 |

변경 파일: `runtime/review/docx_redline.py`, `business_brief.py`, `delivery_docs.py`, `clause_level.py`, `deal_flow.py`,
`cross_border/{findings,engine,perspective,bilingual,checklist_sale}.py`, `runtime/api/server.py`(전달본 409),
`runtime/admin/internal_demo_chat_ui.py`(법무 전용 보류 배너).

## 3. 테스트

- 새 테스트 `runtime/tests/test_brief_delivery_and_table_redline.py`(10건): 합성 국·영 좌우 병기 표 docx 로 셀 안 치환·여러 run 치환·같은 셀 삽입·
  수락/거절 왕복·본문 속 조 인용 무시, 전달본 도구 상태 없음·도구 실패가 결론을 바꾸지 않음·국문 변경 표시 한 블록·항목 이름·필수수정≠LOW·5개 절,
  관점 판단(사용자 말만), loss_path 구조.
- 전체(`runtime/tests`, 메모리 문제로 두 묶음으로 나눠 앞에서 실행): **22 failed, 1889 passed, skipped 0** — 실패 22건은 기준선(156a)과 같은 테스트, 새 실패 0.

### 기존 테스트 기대값 변경 (이번 지시에 따른 동작 변경)

| 테스트 | 변경 전 기대 | 변경 후 기대 | 사유 |
|---|---|---|---|
| `test_business_brief::test_held_rewrite_is_disclosed_with_impact_not_hidden` | 보류된 HIGH 수정이 있으면 판단이 "진행 보류…" | 판단은 계약 리스크로("조건부 진행 가능"), `delivery_blocked` = True·사유 기록, 사유 문구는 전달본 본문에 없음 | 도구 실패가 결론을 바꾸지 않게(지시 2) |
| `test_business_brief::test_sections_in_order_and_no_internal_codes` | 절 이름 "2. 쟁점별 검토 / 4. 사업부 결정사항", "수정 전:/수정 후:" 줄, "문장 추가" 표기 | 절 이름 "2. 체결 전 필수 확정 사항 / 3. 쟁점별 요약 / 4. 계약 전 확인사항", 수정 전/후 줄 없음, 변경 표시 `[+ … +]` 유지 | 목표 형태(지시 5)·변경 표시 한 블록(지시 3) |
| `test_ndg_clause_linkage_and_tracked_changes::BriefCardsTest` | 스타일 "b"(수정 전)·"a"(수정 후) 있음 | "b"·"a" 없음, "d"(변경 표시) 있음 | 지시 3 |
| `test_verification_output_control::test_failed_verification_restricts_every_output` | 검증 미통과면 전달본 판단 = "검증 미통과 초안", 전달본에 "⚠ 미해결" | 판단은 계약 리스크, `delivery_blocked`·법무 화면 보류 표시, 전달본에 "검증 미통과"·"⚠ 미해결" 없음(변경추적본·클린본의 미통과 표지는 그대로) | 지시 2 |
| `test_verification_output_control::test_removed_edit_never_reaches_tracked_or_clean_and_brief_shows_it` | 전달본에 "수정안을 빼고 원문을 유지함" | 전달본에 없음, 검증 기록(`verification.removed`)에는 있음, 뺀 수정 문구는 전달본에 없음 | 도구 상태는 법무 내부에만(지시 2) |

`output_consistency` 의 "미통과면 최종·서명 판정 없음" 검사는 "미통과면 전달본 보류" 로 바뀌었다(같은 목적 — 검증 미통과 결과가 사업팀에 나가지 않음).
기존 회귀 테스트 `test_international_sale_of_goods_regression::test_pre_signing_checks_present` 는 선적 기한이 2절(체결 전 필수 확정)로 옮겨진 배치에 맞췄다.

## 4. 남은 한계

1. Word(DOCX) 전달본 쪽수는 재지 않았다(PDF 3쪽). DOCX 는 같은 줄 구성이며 범례를 한 번만 넣도록 맞췄다.
2. 국내 계약 전달본은 거래 흐름 절(0-x, 임대차·개인정보 흐름)을 계속 싣는다 — 그 절이 있는 계약은 2~3쪽을 넘을 수 있다.
3. 앱(AI 포함)으로 이 계약을 다시 생성하지 않았다. AI finding 이 함께 나오면 쟁점 수·쪽수가 늘 수 있다(같은 게이트를 거친다).
4. 레드라인 엔진의 여러 run 치환은 범위 안에 줄바꿈·탭·그림이 있으면 포기하고 보류로 알린다(그 경우 전달본은 보류된다).
