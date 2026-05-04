# 216. 2단계 AI 계약 이해(fast → deep) 구조

## 목적
- “계약 전체 맥락을 이해한 뒤 핵심 조항만 정밀 검토”하면서도, 응답 속도를 크게 악화시키지 않는다.

## 현재 파이프라인(구현)
### Fast stage
- 목표: 5~10초 내 1차 결과(룰 기반 screening + 컨텍스트 생성)를 빠르게 제공
- 특징:
  - AI off / 법령검색 off
  - final_review_context 생성(사용자 중점 이슈 + 질문 답변 + 국내/해외 + 계약 프로파일)
  - deep review shortlist 후보를 meta에 포함
- 엔드포인트/구현:
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py) `/api/review/analyze_fast`
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `run_review_with_session_fast`
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py) `deep_review_shortlist_clause_ids`

### Deep stage
- 목표: fast 결과 기반으로 “핵심 조항”을 AI 정밀 검토
- 특징:
  - AI on(설정 시) / 법령검색 on(설정 시)
  - user_focus_hit, high_risk, factual_hit 등을 기반으로 deep review 대상 조항을 우선 선정
- 엔드포인트/구현:
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py) `/api/review/analyze_deep`
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `run_review_with_session`

## 기대 효과
- 전체 조항에 무작정 AI를 적용하지 않고 “중점 이슈/고위험/핵심 토픽” 중심으로 deep stage 비용을 집중한다.

