# 163. issues=0 / revision.items=[] 인 경우 DOCX fallback(검토 메모) 출력 보강

## 문제
- 앱 개발계약서에서 `issues=0` 또는 `revision.items=[]`이면:
  - 수정 권고 조항(redline)이 없고,
  - DOCX가 “변경된 조항이 없습니다” 중심으로만 구성되어 법무팀 관점에서 정보 밀도가 낮았다.
- 또한 `/api/revision/download_docx` non-session 호출에서 `clause_results=[]`이고 `original_clauses`가 없으면, 텍스트 길이 부족으로 DOCX 생성이 실패할 수 있었다.

## 목표
1) issue가 0개라도 “검토 메모 Word”를 생성 가능하게  
2) issue가 있으면 기존처럼 clause별 수정 제안 Word 생성  
3) Word 문서에 섹션 포함
   - 핵심 쟁점 요약
   - 검토된 주요 조항
   - 수정 권고 조항
   - 관련 법령
   - 추가 확인 필요 질문
4) 완전 빈 문서처럼 보이지 않게 하기

## 변경 사항
### 1) DOCX 본문 섹션 확장
- 파일: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- `build_revision_docx()`에 optional 입력을 추가:
  - `review_summary`
  - `law_search`(contract scope)
  - `questions`(추가 확인 필요 질문)
- 변경 조항이 0개여도 다음 섹션이 항상 출력되도록 구성:
  - 2) 핵심 쟁점 요약
  - 3) 검토된 주요 조항
  - 4) 수정 권고 조항
  - 5) 관련 법령
  - 6) 추가 확인 필요 질문
  - 7) 본문 redline(변경 조항만 표시)

### 2) `/api/revision/download_docx`에서 fallback 입력 보강
- 파일: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- session 기반 호출:
  - 계약 전문으로 contract-scope law_search 및 질문을 생성해 DOCX에 포함한다.
- non-session 호출:
  - `clause_results=[]`이고 `original_clauses`가 없더라도, `contract_text`(또는 `text`)를 받으면 `(전체)` 1개 조항으로 묶어 검토 메모 DOCX를 생성한다.

## 검증
- 단위 테스트 추가:
  - [test_revision_docx_fallback.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_revision_docx_fallback.py)
  - 변경 조항이 없어도 DOCX가 생성되고, 요구 섹션 문구가 document.xml에 포함되는지 확인한다.

