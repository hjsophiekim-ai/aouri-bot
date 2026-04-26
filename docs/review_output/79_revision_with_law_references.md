# 수정 제안(/api/revision/suggest_text) + 법령 근거 연결

목표:
- 수정 제안할 때 rule 근거뿐 아니라 관련 법령/판례/해석례를 함께 제시
- AI(OpenAI)가 있으면 설명/문안 다듬기만 수행

---

## 변경 내용

- `/api/revision/suggest_text` 응답에 `law_search` 필드를 추가했습니다.
- 구현 위치: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

응답 구조(요약):
1. 원문 조항: `revision.clauses[*].original_text` (기존 구조)
2. 검출 issue: `review_summary + matched_rules` (기존 구조)
3. 적용 rule: `matched_rules` (기존 구조)
4. 관련 법령/판례: `law_search` (신규)
5. 수정 제안 이유/추천 수정문안: `revision` (기존 구조 + AI가 있으면 문구 다듬기)
6. approval required 여부: `review_summary.approval_required` (기존 구조)

---

## 실패/비활성화 시

- `LAW_API_ENABLED=false` 또는 키 미설정이면 `law_search.enabled=false`로 반환됩니다.
- 법령 API 오류가 나더라도 수정 제안 자체는 기존 deterministic 결과로 유지됩니다.

