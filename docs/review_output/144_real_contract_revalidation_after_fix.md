# 144) 실제 계약서 재검증 (수정 후)

검증 대상(요청):
- 일룸/데스커 DESKER MATE 위탁거래 계약서
- track changes가 있는 문서
- 실제 최종 수정본 docx

현재 작업 디렉터리(`c:\Users\FURSYS\Desktop\aouribot`) 기준으로 위 파일이 존재하는지 검색했으나, 해당 계약서 원본을 확인하지 못했습니다.  
따라서 **실제 파일 기반 재검증(업로드→질문→clause→grounding→rewrite→docx 다운로드)**을 수행할 수 없는 상태입니다.

---

## 1) 수정 후 재검증 체크리스트(실행 절차)

1. 서버 실행
2. `/upload`로 해당 docx 업로드(또는 `/demo`에서 업로드)
3. 업로드 응답의 `question_session_id` 확인
4. 질문이 계약 내용에 따라 3~5개로 달라지는지 확인
5. `POST /api/question_sessions/{id}/review` 실행
6. 응답의 `clause_meta` 확인
   - `warnings`에 `word_xml_markers_detected_block`가 없어야 함
   - `clause_extraction_report.strategy`가 `heading`이면 이상적
7. `clause_results[*].original_text`에 `w:rPr`, `w:delText`, `<w:` 등의 문자열이 없는지 확인
8. `clause_results[*].related_laws`가 조항/이슈와 직접 관련되는 title 중심으로 2~3개 이하인지 확인
9. `clause_results[*].suggested_rewrite`가 fallback 복붙이 아니라 조항에 맞게 최소 수정 형태인지 확인
10. `POST /api/revision/download_docx`로 docx 생성
11. 생성 docx를 Word로 열어:
   - 본문에 `<w:...>` 같은 문자열이 보이지 않는지
   - 깨짐/복구 경고가 없는지 확인

---

## 2) 필요한 입력

이 문서를 “실제 검증 결과”로 완성하려면, 문제가 된 계약서를 현재 repo 경로 하위에 제공해야 합니다.
- 권장 위치: `docs/review_input/` (신규 폴더)
- 파일명 예: `DESKER_MATE_위탁거래_TrackChanges.docx`

