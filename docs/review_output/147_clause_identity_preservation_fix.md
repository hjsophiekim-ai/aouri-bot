# 147) clause identity 보존/검증 강화

문제(요청):
- 조항 제목과 수정문안이 엇갈려(예: 보증 조항에 면책 문안, 해제/해지 조항에 손해배상 문안) 보이는 현상
- clause_id, clause_title, article_number가 rewrite 전후로 보존되지 않거나, 다른 clause로 덮어씌워질 위험

목표:
1) clause_id, clause_title, article_number를 rewrite 전후로 반드시 보존  
2) rewrite 결과가 다른 clause로 덮어씌워지지 않도록 보호  
3) issue 템플릿이 clause identity를 침범하지 않도록 수정  
4) 동일 issue_type이 여러 조항에 걸쳐도 조항별 원문 기준으로 따로 rewrite  
5) clause_title mismatch 발생 시 출력 전에 검증 실패 처리

---

## 1) article_number 추가 및 보존

- 조항 구조체에 `article_number`를 추가했습니다.
- 파일:
  - [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
  - [revision.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py) (docx 다운로드 시 original_clauses에 포함)
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py) (표/헤더에 반영)

효과:
- rewrite 전/후 데이터에서 조항 식별자가 보존되고,
- docx 출력에서도 “제N조” 중심으로 표시되어 매핑이 명확해집니다.

---

## 2) clause_id 중복 방지(덮어쓰기 방지)

실제 계약서에서 동일한 `제1조`가 반복(부칙/별첨 등)되는 경우, 이전에는 clause_id 충돌 위험이 있었습니다.

- 개선:
  - 같은 clause_id가 다시 나오면 `KR-1.D2` 같은 형태로 자동 disambiguate
- 구현: [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)

---

## 3) title mismatch 검증 실패 처리(출력 전 차단)

- clause_level에서 `clause_id -> expected_title`을 만든 뒤,
  - revision 결과(clause_results)의 title과 다르면 즉시 block 처리합니다.
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - `warnings`: `clause_title_mismatch_block`
  - `docx_allowed=false`
  - `clause_identity_mismatches`에 mismatch 목록 포함

---

## 4) 조항별 rewrite 분리 보장

- deterministic rewrite는 입력으로 `clause_text`를 직접 받고, 결과를 같은 clause_id에만 귀속합니다.
- AI rewrite(옵션)도 clause_id로만 업데이트하며, 충돌 방지를 위해 clause_id가 유니크하도록 upstream에서 보장합니다.

관련 코드:
- [revision.py:suggest_revisions](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/revision.py)
- [rewrite_engine.py:propose_clause_specific_rewrite](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

