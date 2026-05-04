# 200) rewrite_reason clause-specific 필터 강화
 
## 문제
 
- 조항별 `rewrite_reason`가 여러 토픽 문장을 기계적으로 붙이면서, 조항과 무관한 이유가 섞이는 문제가 있었다.
- 특히 “중복 취지로 판단…” 문구가 실제 rewrite가 없는 조항에도 붙을 수 있었다.
 
## 해결
 
- `keep_as_is` 조항은 `rewrite_reason`를 고정 문구로 설정하고, 이후 자동 reason 생성/중복 통합 로직을 적용하지 않는다.
- 자동 reason 생성 시:
  - 직접 관련 정보만 최대 2개까지만 요약(이슈/규칙/법령)
  - “중복 대표 반영” 문구는 **실제로 dedup으로 인해 rewrite가 제거된 조항**에만 부여
  - rewrite가 없으면 “중복…” 문구를 붙이지 않는다.
 
## 구현 위치
 
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - keep_as_is 조항 처리
  - reason 생성 시 최대 2개 제한 및 keep_as_is 제외
 
