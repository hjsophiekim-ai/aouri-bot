# 169. /api/review/analyze 메인 경로에서 AI 활성화(불일치 제거)

## 문제
- `/api/review/analyze`는 AI provider를 만들더라도 clause-level 엔진 호출 시 AI 파라미터가 전달되지 않으면,
  - 메인 분석 결과가 AI 없이 동작하고,
  - `/api/revision/suggest_text` 결과와 품질 차이가 크게 벌어진다.

## 목표
1) `/api/review/analyze`에도 실제 ai_provider 전달  
2) ai_model/timeout/max_tokens/temperature 함께 전달  
3) 화면의 review 결과와 revision 결과 품질 차이를 줄이기  
4) clause-level rewrite reason / minimal-change suggestion 품질 개선  
5) AI enabled=true인데 analyze가 AI 없이 도는 불일치 제거  

## 적용 내용
- 파일: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- `/api/review/analyze`에서:
  - `ai_provider = create_ai_provider(cfg)` 생성 후
  - `build_clause_level_result(..., ai_provider=ai_provider, ai_model=cfg.model, ai_timeout_sec=cfg.timeout_sec, ai_max_tokens, ai_temperature)`로 전달
  - AI 비활성(키 없음/비활성 설정)인 경우에만 `ai_provider=None`로 fallback

## clause-level AI 품질 보강
- 파일: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- AI rewrite 입력에 `context_text`(상위 조문 맥락)를 포함하여,
  - 하위 항/호만 떼어낸 상태에서도 상위 맥락을 참고해 수정문안을 생성하도록 개선
- AI 출력(문안/사유)에 한국어 후처리(`polish_korean_legal_style`)를 적용하여
  - 조사 어색함/반복/메타 표현 노출을 줄임

## 기대 효과
- 메인 analyze 화면에서도 AI rewrite가 실제로 반영되어,
  - revision 결과와의 품질 갭이 축소되고,
  - “최소 변경” 원칙에 가까운 문안이 더 잘 생성된다.

