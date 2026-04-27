# 181) API 효과 검증(자동)

- base_url: `http://127.0.0.1:8787`
- generated_at: `2026-04-27 14:43:55`

## 케이스 요약

- ai=auto, law=auto: ai_used=True, ai_selected=8, law_enabled=True, law_queries=4, law_refs=3, clause_law_refs=16, clause_law_nonempty=8, clauses=8, rewrites=8, changed_segments=1
- ai=off, law=auto: ai_used=False, ai_selected=0, law_enabled=True, law_queries=4, law_refs=3, clause_law_refs=16, clause_law_nonempty=8, clauses=8, rewrites=8, changed_segments=0
- ai=auto, law=off: ai_used=True, ai_selected=8, law_enabled=False, law_queries=0, law_refs=0, clause_law_refs=0, clause_law_nonempty=0, clauses=8, rewrites=8, changed_segments=1
- ai=off, law=off: ai_used=False, ai_selected=0, law_enabled=False, law_queries=0, law_refs=0, clause_law_refs=0, clause_law_nonempty=0, clauses=8, rewrites=8, changed_segments=0

## 판정 기준(요지)

- AI 효과: ai_mode=auto/on에서 ai_used=true이고, ai_mode=off 대비 rewrites/changed_segments가 증가 또는 품질 지표가 개선되는지 확인
- Law 효과: law_mode=auto/on에서 law_enabled=true이며, law_mode=off 대비 law_refs가 증가하는지 확인
