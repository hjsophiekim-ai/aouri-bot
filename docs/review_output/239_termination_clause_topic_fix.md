# 239. 제23조(해지) 토픽 오분류(topic contamination) 수정 + redline 승격

## 문제
- 제23조 제3항(즉시해지)이 “분쟁해결/재판관할/준거법” 토픽으로 잘못 분류되어
  - 앱 화면 “답변 반영 쟁점”이 분쟁조항으로 연결됨
  - 해지 남용/불이익 제공(대리점법 핵심) 검토가 약화됨

## 목표
- clause topic classifier가 제23조를 termination 중심으로 분류하도록 보정
- 분쟁(dispute) 토픽이 해지(termination) 조항으로 전이되지 않도록 contamination 차단
- 제23조 제3항 review reasoning 축(최소) 반영:
  - 즉시해지 예외 사유 한정
  - 중대한 위반행위 객관화
  - 원칙적 시정기회/상당한 기간
  - 예외적 무최고 해지 사유를 좁게 열거
- 제23조 같은 핵심 조항은 guidance가 아니라 구체적 redline candidate 생성 대상으로 승격

## 적용 변경(코드)
- 토픽 분류 tie-break: termination 신호와 dispute 신호가 함께 있으면 termination 우선
  - [clause_topic.py:classify_clause_topic](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_topic.py#L23-L68)
- dealer 계약에서 제23/24조가 dispute로 떨어질 경우 termination으로 보정(안전장치)
  - [clause_level.py (dealer override)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L660-L689)
- dealer 핵심 조항(23/24)에 대해 구체적 redline 후보 문안 + 방향/사유를 강제로 생성(제안 문안이 비면 생성 실패로 이어짐)
  - [clause_level.py (dealer redline candidate)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L894-L929)

## 기대 효과
- 제23조 제3항이 dispute로 분류되어 “분쟁해결/관할” 이슈로 전이되는 현상 차단
- 제23조 제3항은 termination/불이익 제공(해지 남용 통제) 축으로 구체 redline이 생성됨

