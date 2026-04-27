# 151) 최종 Word 문서 가독성 업그레이드

목표:
- 법무팀이 “무엇이 왜 바뀌었는지” 바로 이해 가능한 형태로 DOCX를 구성
- 동일 문단 반복 출력 방지
- clause 번호/제목/원문/수정문/사유의 관계를 명확히

---

## 1) 현재 DOCX 구성(최소 MVP 충족)

DOCX는 아래 섹션으로 구성됩니다.
1) 표지/요약  
2) 본문 redline(변경 조항만)  
3) 조항별 수정 사유 부록(표)  
4) High risk / Approval required 표  

구현: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

---

## 2) 가독성 개선 포인트(이번 반영)

- 조항 헤더에 `article_number`를 우선 표기해 “제N조” 중심으로 읽히게 개선
  - clause_id가 내부 키로 쓰이더라도, 출력은 조항번호 기반으로 보이도록 함
- redline에서 “변경 토큰만” 빨강/취소선 처리(전체 문단이 빨갛게 보이는 문제 완화)

관련 변경:
- [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- [150_docx_true_redline_diff_fix.md](file:///c:/Users/FURSYS/Desktop/aouribot/docs/review_output/150_docx_true_redline_diff_fix.md)

---

## 3) 추가 개선(후속)

실제 LG 계약서(docx)로 재검증하면서 다음을 추가로 조정하는 것이 안전합니다.
- “핵심 리스크 요약” 문구를 issue_title 기반으로 더 정돈
- 변경 조항의 정렬을 원문 순서 기반으로 유지(현재는 clause_id 정렬 + 위험도 우선)
- 부록 표의 열 너비/줄바꿈 최적화

