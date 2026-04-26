# 126. Clause Extraction 레이어 고도화

## 목표
- 계약서 본문을 article/clause 단위로 분해
- 한글/영문 조항 패턴 최대한 인식
- 문단형 계약서 fallback 분리
- 조항별 ID, 제목, 본문을 갖는 배열 구조 제공

## 구현 위치
- 조항 분해 함수: [revision.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/revision.py) `split_into_clauses()`

## 지원 패턴(핵심)
### 1) 한글 조항
- `제1조`, `제 2 조` 등
- `제3조(정의)`처럼 괄호 제목 포함 가능

### 2) 영문 조항
- `Article 1`, `ARTICLE II` 등 (숫자/로마숫자)

### 3) 번호형 조항(문단 내 조항)
- `1.`, `2)`, `(3)` 같은 번호형 헤딩을 조항 경계로 인식

### 4) 문단형 fallback
- 위 패턴이 하나도 잡히지 않으면 빈 줄 기준으로 문단을 분리(`P-001`, `P-002` …)
- 문단이 과도하게 긴 경우(예: 추출 품질 저하로 줄바꿈 없음) 최대 길이 단위로 추가 분할

## 출력 구조(Clause 배열)
- `ClauseChunk[]`
  - `clause_id`: `C-001` 또는 `P-001` 형태의 내부 ID
  - `title`: 추출된 제목(예: `제10조(손해배상)` / `Article 2 Confidentiality` / `1. Payment`)
  - `text`: 해당 조항의 원문 블록(여러 줄 포함 가능)

## 후속 활용
- 조항별 분석/수정 엔진은 `split_into_clauses()` 결과를 기반으로 `clause_results`를 생성합니다.
- 위치: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
