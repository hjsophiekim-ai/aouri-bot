# 138) 계약서 clause extraction 재설계/구현

문제:
- clause가 실제 조항이 아니라 긴 문단/설명문/XML 파편 단위로 잡히며,
- 그 결과 질문/법령 grounding/수정제안/Word 출력까지 연쇄적으로 품질이 무너지는 현상이 발생.

목표:
- 제1조, 제2조, Article 1, 1., (1), 가., 나. 구조를 최대한 보존
- 제목/본문 분리
- clause_id 안정화
- 너무 긴 문단은 서브클로즈로 분리
- XML/스타일 정보가 섞인 문단은 걸러내기
- 조항별 clean_text 저장
- 검증 리포트 생성

---

## 1) 구현 파일

- 조항 파서: [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
- clause-level 결과에 리포트 포함: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

---

## 2) 파서 구성(필수 구현 항목 대응)

### 2.1 한글 계약서 조항 파서

- 헤딩 패턴:
  - `제N조`, `제N조의M` + 옵션 `(제목)`  
- clause_id:
  - `KR-1`, `KR-1-2` 형태(숫자 기반)

구현: [extract_clauses](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py#L74-L196)

### 2.2 영문 조항 파서

- 헤딩 패턴:
  - `Article 1`, `Article IV` 등
- clause_id:
  - `EN-ARTICLE-1` 등

구현: 동일 함수 내 영문 헤딩 매칭

### 2.3 fallback paragraph splitter

- 헤딩을 찾지 못하면 빈 줄 기준 문단 분리 + 길이 기반 chunking
- clause_id:
  - `P-001`, `P-002` 등

구현: [_fallback_split](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py#L199-L224)

### 2.4 조항 길이/품질 검사

- WordprocessingML 마커가 있으면 “blocked”로 즉시 중단
- 라인 단위로 XML/태그 조각을 제거/드랍
- 너무 긴 조항은 하위 번호 패턴으로 서브 분리 시도(실패 시 fallback 분할)

구현:
- 마커 탐지: [word_markers.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/word_markers.py)
- 라인 클리닝: [_clean_lines](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py#L57-L72)
- 서브 분리: [_split_by_subclauses](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py#L227-L255)

### 2.5 조항별 clean_text 저장

- 현재 구조에서는 `ClauseChunk.text`가 clean_text 역할을 합니다(조항 텍스트 자체가 클린 결과).
- (추후 확장) `raw_text`/`clean_text`를 모두 저장하는 구조로 쉽게 확장 가능.

### 2.6 clause extraction 결과 검증 리포트 생성

- `ClauseExtractionReport` 생성 및 `clause_meta.clause_extraction_report`에 포함
- 포함 필드:
  - strategy(heading/fallback/blocked)
  - clause_count, headings_found, fallback_only
  - dropped_lines, split_long_clauses, warnings

구현:
- 리포트 타입: [ClauseExtractionReport](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py#L23-L46)
- meta 반영: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L302-L315)

