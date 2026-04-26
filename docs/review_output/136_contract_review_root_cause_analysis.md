# 136. Contract Review Root Cause Analysis (Engine)

## TL;DR
- 입력 텍스트 오염(WordprocessingML XML 조각 유입) + 질문/법령/수정문안이 “조항 기반”이 아닌 “계약유형/룰ID 기반”으로 동작하면서 계약별 정밀도가 떨어졌다.
- 현재는 1차 관문(추출)과 2차 관문(review/docx)에서 WordprocessingML 마커를 강하게 차단하고, rewrite/docx 생성 로직을 조항 기반으로 바꿔 “깨진 XML이 본문으로 보이는 문제”를 구조적으로 막았다.
- 남은 핵심 갭은 (1) PDF/HWP 실추출 (2) clause extraction 품질(긴 문단/설명문 혼입) (3) issue-type 쿼리 템플릿 기반의 더 강한 clause-aware law_search 정밀화다.

---

## 1) 업로드된 docx/pdf/hwp가 어떤 파이프라인으로 텍스트화되는지

### 공통: `/api/upload` → `extract_text_from_file()` → 세션 저장
- 업로드 엔드포인트: [server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py) 의 `_handle_upload`
  - 업로드 파일을 임시 저장 후 `extract_text_from_file(p)` 호출
  - 성공 시 `create_session(..., text=extraction.text, ...)`로 **세션에 “추출 텍스트”를 원문으로 저장**

### DOCX: zip(OOXML) 내부 WordprocessingML을 “visible text”로 파싱
- 추출 구현: [text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py)
  - `extract_text_from_docx()`가 `word/document.xml` + header/footer/notes를 대상으로 파싱
  - `_extract_visible_text_from_word_xml(..., track_changes_policy="final")`
    - 문단(`w:p`) 단위로 텍스트 노드만 수집
    - Track Changes 정책 기본값(final): 삭제(`w:del*`) 제외, 삽입(`w:ins`) 포함
  - **추출 결과 텍스트에 WordprocessingML 마커가 남으면 extraction 단계에서 실패 처리**

### PDF/HWP: 현재 “미지원(추출 실패)”로 처리
- `extract_text_from_file()`는 `.pdf`를 `pdf_unsupported_mvp`로 실패 처리([text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py))
- 업로드 응답도 “OCR/hwp/pdflayer backlog”로 안내([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py))

---

## 2) 실제 review analyze에 들어가는 입력이 무엇인지

### (A) 세션 기반(권장): 업로드 텍스트가 그대로 입력
- `/api/upload`에서 만든 세션은 `doc["text"]`에 추출 텍스트를 저장([storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py))
- `/api/question_sessions/{id}/review` 경로에서 `doc["text"]`를 읽어 `build_clause_level_result(..., text=text, ...)`로 전달([storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py))

### (B) 직접 호출: `/api/review/analyze` body.text가 입력
- `/api/review/analyze`는 body의 `text`를 그대로 `build_clause_level_result()`에 전달([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py))
- 여기서 **WordprocessingML 마커가 포함된 텍스트는 400으로 거절**한다(“docx markup must not be analyzed” 차단)

---

## 3) clause extraction 전에 어떤 cleaning/normalization을 거치는지

### 텍스트 추출 단계(업로드 직후)
- `text_extract._strip_zero_width_and_ctrl()`로 제로폭/제어문자 제거
- `text_extract._norm_text()`로 공백/빈줄 정규화

### clause extraction 단계(조항 분해 직전)
- 조항 분해는 `split_into_clauses(text)`에서 시작([revision.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/revision.py))
- `split_into_clauses()` 내부에서 `_clean_contract_text()` 수행:
  - 줄 단위로 WordprocessingML 마커가 섞인 라인을 제거
  - `<prefix:...>` 같은 “태그만 있는 라인” 제거
  - 공백/빈줄 정규화

---

## 4) 질문 생성기가 어떤 입력을 기준으로 질문을 고르는지

### 현재(개선 후): contract_text + clause_results + detected_rule_ids
- 세션 생성 시:
  - `build_clause_level_result(..., max_clause_law_items=0)`로 조항/룰 매칭을 먼저 만든 뒤
  - `generate_questions(..., contract_text=text, clause_results=bundle.clause_results, max_questions=5)` 호출([storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py))
- 질문 엔진: [generator.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
  - 계약 텍스트의 키워드 존재 여부(예: “판촉비/반품/위탁판매”, “개인정보/위탁” 등) + 조항별 적용 룰ID를 함께 사용해 상위 질문을 우선 선정
  - 질문 수는 3~5개로 제한(부족하면 baseline 1~2개로 보강)

### 과거(문제 원인)
- 질문이 계약 본문/조항과 직접 연결되지 않고 `entity/contract_type/detected_rule_ids` 중심으로 고정되어 계약별 차별화가 약해졌다.

---

## 5) law_search가 어떤 키워드/토픽으로 검색하는지

### 토픽 생성: contract_type + 텍스트 키워드 + matched_rules
- 구현: [search_service.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
  - `_derive_topics(entity, contract_type, text, matched_rules)`에서
    - 계약유형(대리점/하도급/개인정보/광고/안전 등)
    - 원문 텍스트 포함 키워드
    - 매칭된 룰ID에 따른 추가 토픽(예: RISK-006 → 대리점법/판촉비/반품 등)
  - 상위 3개 쿼리로 검색(성능/노이즈 관리 목적)

### 결과 정밀화(개선): 노이즈 제거 + 간이 rerank
- `_rerank_and_filter_references(...)`를 통해
  - “광고/홍보/조례안/입법예고” 등 노이즈 타이틀 제거
  - 컨텍스트(조항 텍스트 + 룰 키워드)와 title/snippet의 토큰 overlap 점수로 재정렬
  - 점수 낮은 결과 제거(최소 관련성 기준)

---

## 6) docx 최종 출력이 원문 텍스트가 아니라 XML 문자열을 받고 있는지

### 최종 생성 경로
- 다운로드 엔드포인트: `/api/revision/download_docx`([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py))
  - 세션 기반으로 `build_clause_level_result()`를 재실행하고
  - `build_revision_docx(original_clauses, clause_results)`로 DOCX 생성([docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py))

### “XML 문자열 혼입”의 실제 원인(과거)
- 원문 텍스트가 이미 오염되어(`<w:...>` 같은 마커가 clause text로 유입) 그것이 그대로 docx 본문 텍스트로 출력되는 케이스.
- docx writer가 “문서 XML”을 문자열로 조립하는 과정에서, 입력 텍스트가 부정확하게 escape/조립되면 깨질 수 있는 구조.

### 현재 방어(개선 후)
- 입력(추출/분석) 단계에서 WordprocessingML 마커를 강하게 차단:
  - 추출 단계: `extract_text_from_file()`가 마커 감지 시 실패([text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py))
  - 분석 단계: `/api/review/analyze`가 마커 감지 시 400([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py))
  - clause_level 결과에서도 원문에 마커가 있으면 필터링([clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py))
- 출력 단계에서 “객체 기반 생성 + 텍스트 마커 차단”:
  - docx writer가 ElementTree로 문서 객체를 만들고 직렬화
  - `w:t`에 들어가는 텍스트에 마커가 있으면 ValueError로 실패 처리([docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py))

---

## 증상별 Root Cause (코드 흐름 기준)

### (1) 계약별 질문이 generic
- 원인 레이어: 질문 생성기 입력이 계약 조항/이슈가 아닌 `entity/contract_type/detected_rule_ids` 중심으로 고정되면 질문이 수렴한다.
- 개선 레이어: 세션 생성 시 `build_clause_level_result()`로 clause_results를 만든 뒤, `contract_text + clause_results` 기반으로 3~5개만 고른다([storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py), [generator.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)).

### (2) 원문 조항에 Word XML 태그가 섞여 깨짐
- 원인 레이어: DOCX 텍스트화에서 XML을 “텍스트로” 잘못 흘리거나, Track Changes 처리 정책 없이 삭제/삽입 영역을 섞어서 추출하면 clause 텍스트에 `<w:...>` 조각이 들어갈 수 있다.
- 개선 레이어:
  - DOCX 추출을 구조 파싱으로 고정하고 마커 잔존 시 실패 처리([text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py))
  - clause 분해 전 `_clean_contract_text()`로 태그성 라인 제거([revision.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/revision.py))

### (3) 관련 법령/판례가 직접 관련 없는 것도 섞임(grounding 낮음)
- 원인 레이어:
  - 토픽이 넓거나(예: “공정거래” 등) re-rank/필터 없이 title 리스트만 붙이면 노이즈(광고/조례안/무관 판례)가 섞일 수 있다.
- 개선 레이어:
  - 노이즈 타이틀 제거 + 컨텍스트 overlap 기반 rerank/필터 적용([search_service.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py))
- 남은 과제:
  - issue_type별 쿼리 템플릿(“비용전가/책임상한/개인정보 위탁/안전” 등)로 더 좁은 검색어 구성
  - clause 텍스트 기반으로 “조항별 top 2~3개”만 유지하는 강한 제한

### (4) 최종 Word 파일도 XML 조각이 본문으로 들어가 깨짐
- 원인 레이어:
  - 입력 텍스트가 오염되면(원문/수정문/이유에 `<w:` 등) docx 본문 텍스트로 그대로 출력될 수 있다.
  - 문자열 조립 방식은 escape/구조 결함에 취약하다.
- 개선 레이어:
  - docx 출력기를 ElementTree 기반 “문서 객체 생성”으로 교체하고, 텍스트에 마커가 있으면 생성 자체를 실패 처리([docx_writer.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py))

---

## 어디 레이어에서 깨지는가(요약)
- 입력 오염 발생 지점(핵심): DOCX 텍스트 추출([text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py))
- 오염 증폭 지점: clause extraction(오염된 라인이 조항으로 잡힘) + UI/결과 렌더링
- 최종 폭발 지점: docx 출력(오염된 텍스트가 본문 텍스트로 들어가면 깨짐)

---

## 무엇을 먼저 고쳐야 하는지(우선순위)
1. **입력 오염 차단(완료)**: DOCX “visible text” 추출 + WordprocessingML 마커 검증 실패 처리
2. **출력 파이프라인 차단(완료)**: docx writer 객체 기반 생성 + 텍스트 마커 차단
3. **조항 맞춤형 rewrite(완료)**: 템플릿 복붙 제거 + clause-specific deterministic fallback
4. **질문/법령 정밀화(부분 완료)**:
   - 질문: 계약 텍스트/조항 기반 top 3~5개(부분 완료)
   - 법령: 노이즈 제거/rerank(부분 완료), issue-type 템플릿/강한 clause-aware 제한은 추가 개선 필요
5. **PDF/HWP 추출(미완료)**: 실제 운영 계약서가 PDF/HWP면 현재는 본문이 비어 shallow로 이어질 수 있어 최우선 backlog

