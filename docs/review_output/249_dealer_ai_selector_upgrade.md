# 249. dealer 전용 AI deep review selector 업그레이드

## 목표
- dealer 계약에서 AI deep review 대상을 generic risk_tier 중심이 아니라 “대리점 핵심 조항 + user_focus 우선”으로 선정한다.
- 국내 대리점에서 제27조(분쟁/관할)는 사용자 요청/크로스보더 정황이 없으면 감점한다.

## 변경(코드)
- AI deep review scoring에 dealer 전용 가중치/감점 규칙 추가:
  - [clause_level.py:_score_for_ai_deep_review](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L470-L515)
  - 핵심 조항(21/23/14/11/17/8~10) +120
  - termination/dealer_unfair/cost_burden/payment_settlement 토픽 +45
  - 국내+비요청 분쟁(dispute/제27) 감점

