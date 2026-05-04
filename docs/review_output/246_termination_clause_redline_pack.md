# 246. 제23조(해지) 전용 redline pack(termination)

## 목표
- 제23조 제3항 같은 즉시해지 조항을 dispute(관할/준거법)로 섞지 않고 termination 축으로 고정한다.
- guidance 수준이 아니라 바로 넣을 수 있는 구체 redline candidate를 생성한다.
- 결과 데이터에 아래 필드를 포함한다.
  - original_text / suggested_rewrite / changed_segments / rewrite_reason / why_this_is_core_issue / related_laws

## 변경(코드)
- 토픽 오염 차단(termination 우선 + dealer 제23/24 강제 termination):
  - [clause_topic.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_topic.py#L23-L57)
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L660-L674)
- 제23/24조 redline 후보 강제 생성(즉시해지 예외 한정/객관화/시정기회/무최고 해지 좁게 열거):
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L894-L930)
- changed_segments 자동 보정(문안 생성형 결과에도 diff 기반 preview 제공):
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L1410-L1420)

