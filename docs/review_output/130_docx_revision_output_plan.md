# 130. DOCX 수정본 출력(Revision Output) 구현 계획

## 목표
- 업로드된 계약서(또는 추출된 텍스트)를 기준으로 최종 수정본 `.docx`를 생성
- 수정된 조항은 강조 표시(색상/밑줄/볼드/하이라이트 등)
- 수정 이유를 문서에 포함
- 원문/수정문 비교가 가능하도록 구성
- 다운로드 가능

## MVP 설계(Track Changes 대신 Redline/병기형)
### 1) 문서 구성(한 파일에 모두 포함)
1. 표지/메타: 법인, 계약유형, 파일명
2. 원문 계약서 Clean Copy
3. 수정본(조항별) + 수정 조항 강조
4. 부록: 조항별 원문/수정문/이유 표

### 2) 강조 표시 방식(MVP)
- “추천 수정문안” 전체를 다음 스타일로 표시
  - 빨간색 글씨 + 밑줄 + 볼드 + 노란 하이라이트
- 원문은 일반 텍스트로 표시
- 수정 이유는 조항 아래 “수정 이유:” 섹션으로 표시

### 3) 원문/수정문 매핑 기준
- clause extraction으로 생성된 `original_clauses[]`(문서 전체 조항)를 Clean Copy/수정본의 기준으로 사용
- `clause_results[]`는 “수정 제안이 있는 조항”만 포함하므로, `clause_id`로 매핑하여 해당 조항만 수정문안을 추가 표기

## 구현 범위
### A. DOCX 생성기
- 파일: [docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- 외부 라이브러리 없이, 최소 OOXML(`word/document.xml`)을 zip으로 구성
- 표는 WordprocessingML `<w:tbl>`로 생성(부록 표)

### B. 다운로드 엔드포인트
- `POST /api/revision/download_docx`
  - `{ "session_id": "..." }` 기반 생성(업로드 본문 우선)
  - 반환: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- 구현: [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py)

### C. Guardrail(생성 금지/경고)
- 본문이 너무 짧거나 조항 구조가 부족하면(docx_allowed=false) docx 생성 요청을 400으로 차단
- 경고/차단 기준은 `clause_meta.meta.warnings`와 `docx_allowed`로 노출
- 구현: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 다음 고도화(후속)
- 실제 Track Changes(w:ins/w:del) 적용
- diff 기반 “부분 변경”만 표시(현재는 수정문안 전체 강조)
- 업로드 원본이 `.docx`인 경우 원본 서식을 최대한 유지한 상태로 수정 반영(현재 MVP는 텍스트 기반 재생성)
