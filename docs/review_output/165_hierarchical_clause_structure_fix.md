# 165. 계층형 조항 구조(조/항/호/목) 보존 및 표시 개선

## 문제
- 원문 계약서는 `제n조 > 제m항 > 제k호(> 가목)`처럼 계층 구조가 명확한데,
- 기존 clause extraction은 조문/번호/가-하를 평면적인 `clause_id`로만 분할해 하위 항목이 “몇 조인지”만 보이고 맥락이 약해졌다.

## 목표
1) clause extraction을 계층형 구조로 재설계  
2) 원문의 조/항/호/목 번호를 그대로 유지  
3) 앱 화면과 Word에서 `제4조 제4항 1호`처럼 표시  
4) 상위 조문과 하위 세부항목의 관계를 잃지 않게 하기  
5) 세부항목 단독 rewrite가 아니라 상위 조문 context도 함께 보이게 하기  

## 구현 요약
### 1) ClauseChunk에 계층 필드 추가
- 파일: [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
- 추가 필드:
  - `article_number`
  - `paragraph_number`
  - `item_number`
  - `subitem_number`
  - `display_path` (예: `제4조 제2항 1호 가목`)
  - `parent_clause_id`
  - `context_text` (상위 조문/항 맥락 텍스트)

### 2) KR 조문(제n조) 내부를 “항/호/목”으로 계층 파싱
- 조문(제n조) 헤딩을 기준으로 블록을 잡은 뒤, 본문에서:
  - 항: `①`(원형 숫자) 또는 `제n항`/`n항`
  - 호: `1.` / `(1)` / `1)` / `1호`
  - 목: `가.` / `(가)` / `가)` / `가목`
  를 라인 기반으로 감지해 계층 노드를 생성한다.
- 각 노드는 원문 번호를 `display_path`로 보존하고, 하위 노드에는 상위 맥락을 `context_text`로 붙인다.

### 3) 탐지/리라이트에 상위 맥락을 반영
- 파일: [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
- 룰 키워드 매칭은 `context_text + text`를 기준으로 수행하여,
  - 하위 호/목에 표현이 없더라도 상위 항/조의 맥락을 잃지 않게 했다.

### 4) API 결과에 display_path/context_text 포함
- 파일: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- `clause_results[]`에 `display_path`, `context_text`, `parent_clause_id`, `paragraph_number/item_number/subitem_number`를 포함한다.

### 5) Word 출력에서 조항 위치와 상위 맥락 표시
- 파일: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- 변경 조항 헤딩에 `display_path`를 우선 사용하고,
- `context_text`가 있으면 본문 redline 직전에 회색 텍스트로 상위 맥락을 함께 출력한다.

### 6) 앱 데모 화면에서도 조항 위치 표시 강화
- 파일: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- 조항 카드 제목을 `clause_id` 대신 `display_path` 우선으로 표시한다.
- 원문 박스 상단에 `context_text`를 함께 노출한다(요약).

## 기대 효과
- 결과 화면과 Word에서 “제n조/제m항/k호/가목” 위치가 명확해져 하위 세부항목의 맥락이 유지된다.
- 하위 항목 단독으로 보이는 문제를 완화하고, 상위 조문 컨텍스트를 기준으로 더 정확한 검토/수정 제안이 가능해진다.

