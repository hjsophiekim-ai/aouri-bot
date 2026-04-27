# 175) Legal prompt 재설계(실무 redline 지향)

## 배경
- 기존 clause-level AI 호출은 “fallback rewrite 보강” 성격이 강했고, 역할/거래구조/법령 근거를 적극 활용하지 못함
- 변호사식 검토 문체/논리(법률 근거 + 실무 리스크 + 협상 논리)로 rewrite_reason를 만들고, 최소 변경 redline에 적합한 suggested_rewrite를 생성하도록 프롬프트 체계를 강화

## 새 프롬프트 원칙(반영)
- 역할: “한국 기업 법무팀 계약검토 변호사”
- 입력 컨텍스트 활용: `party_role`, `review_posture`, `answers`, `clause_title`, `display_path`, `original_text`, `context_text`, `related_rules`, `related_laws`
- 최소 변경 원칙 강화: 덧붙임보다 기존 문장 치환/삭제/흡수 우선
- 근거 없는 추정 금지: 입력 밖 사실/의무/결론 생성 금지
- 사용자 노출 금지: buyer_favorable 같은 메타 표현 제거(법무 문체로만 출력)

## 출력 스키마(통일)
AI 출력은 반드시 JSON 배열이며, 각 원소는 아래 필드로 통일:
- `clause_id`
- `rewrite_reason`
- `suggested_rewrite`
- `changed_segments`: 최대 3개, `{ "before": "...", "after": "..." }`
- `risk_tier`: 입력값 그대로 echo
- `must_fix`: 입력값 그대로 echo

## 코드 반영
- 프롬프트 및 파서(변경 요약/changed_segments 저장, must_fix 필드 추가):
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 검증 포인트
- `/api/review/analyze` 응답에서:
  - `clause_results[].changed_segments`가 일부 조항에서 채워짐
  - `clause_results[].must_fix`가 HIGH/approval_required에 대응
  - `ai.detail.selected_clause_ids`로 deep review 범위 확인 가능

