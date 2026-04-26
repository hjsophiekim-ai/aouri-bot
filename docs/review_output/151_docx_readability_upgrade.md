# 151. DOCX Readability Upgrade (법무팀 바로 읽는 최종 수정본)

## 목표
- 최종 Word 문서를 법무팀이 “바로” 읽을 수 있는 구조로 재구성한다.
- 중복 섹션(원문 전체 반복 등)을 제거하고, 변경된 조항만 redline으로 보여준다.
- 조항 번호/제목 매핑이 어긋나면 산출물 생성 자체를 실패 처리한다.

## 적용된 문서 구성
1) **표지/요약**
   - 계약명(=파일명), 상대방(미상 시 표기), 계약유형, 법인
   - 핵심 변경 조항 수 / High risk / Approval required 카운트
   - 핵심 리스크 요약(변경 조항 상위 N개)

2) **본문 redline 버전**
   - “변경된 조항만” 출력
   - 동일 조항 내부에서 **변경된 부분만** 빨간색/밑줄(삽입) 또는 빨간색/취소선(삭제)으로 표시

3) **조항별 수정 사유 부록(변경 조항만)**
   - 조항번호/제목
   - 원문 요지(요약)
   - 수정 포인트(추가/삭제 토큰 요약)
   - 수정 이유
   - 관련 법령(최대 3개)

4) **High risk / Approval required 표**
   - 변경 조항 중 High/Approval 표시가 있는 항목만 별도 표로 정리

## 핵심 구현(코드)
- 파일: [docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

### 1) “변경된 조항만” 출력
- `changed_clause_ids`를 계산해 redline/부록/표에 동일 기준으로 사용
- 원문 전체(clean copy) 섹션을 제거하여 중복 문단이 두 번씩 나오지 않도록 함

### 2) 변경 부분만 색상/취소선 처리
- `difflib.SequenceMatcher` 기반 diff로 run 단위를 생성
  - equal: 일반 텍스트
  - insert: 빨간색 + 밑줄
  - delete: 빨간색 + 취소선

### 3) clause 번호/제목 매핑 검증(불일치 시 실패)
- `clause_results`의 `clause_id`가 `original_clauses`에 없으면 `ValueError`
- `clause_title`이 서로 다르면 `ValueError`

### 4) WordprocessingML 마커 차단(최종 산출물 보호)
- 원문/제목/메타에 `<w:` 등 WordprocessingML 마커가 포함되면 docx 생성 단계에서 실패 처리

## 검증(테스트)
- [test_docx_readability_upgrade.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/tests/test_docx_readability_upgrade.py)
  - 변경 조항이 있을 때 red run과 non-red run이 함께 존재(=전체 문장이 빨간색이 아님)
  - clause title mismatch 발생 시 실패

