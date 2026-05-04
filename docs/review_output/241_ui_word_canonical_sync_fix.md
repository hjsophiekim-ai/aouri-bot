# 241. UI/Word 단일 소스(canonical review result) 동기화 + mismatch 차단

## 문제
- UI(조항 카드)와 Word(DOCX) 생성이 서로 다른 결과 객체를 사용하거나, 중간 단계에서 문안이 변경되어 “앱에는 있는데 Word에는 없음”이 발생

## 목표
- UI, DOCX generator, appendix, summary가 동일한 canonical review result를 사용
- 앱 화면의 clause card 항목(이슈/사유/제안 문안/risk tier)이 Word에도 동일하게 반영
- “앱에는 있는데 Word에는 없음” 발생 시 문서 생성 실패 처리
- revalidation report에 mismatch 상세를 남길 수 있도록 오류를 구조화

## 적용 변경(코드)
- DOCX는 `clause_results[*].suggested_rewrite`를 단일 기준으로 사용(문안 1원화)
  - [docx_writer.py:build_revision_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L301-L387)
- DOCX 다운로드 시점의 consistency checker 강화
  - clause_id가 original_clauses에 없으면 실패
  - UI vs DOCX 변경 조항 집합(changed_clause_ids vs has_rewrite_change) 불일치면 실패
  - UI-visible 조항이 DOCX show 대상에서 누락되면 실패
  - UI-visible(HIGH/MEDIUM) 조항에 제안 문안이 없으면 실패
  - [server.py:_handle_revision_download_docx](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py#L1299-L1413)

## 기대 효과
- UI에 노출되는 “참고 문안(제안 문안)”이 Word에도 동일하게 포함됨
- UI/Word 불일치가 재발하면 다운로드 단계에서 즉시 실패하여 신뢰성 저하를 방지함

