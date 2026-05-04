# 233. 대리점 핵심 조항 clause-specific redline 생성 업그레이드

## 목표
- 추상적 guidance가 아니라 실무에서 바로 넣을 수 있는 “구체 문안(suggested_rewrite)”을 생성
- 특히 제21(불공정/지위남용), 제23(해지) 등 핵심 조항은 자동 승격 및 문안 제공

## 적용 변경(대리점 계약)
### 1) 제23조(계약해지) redline candidate 강제 생성
- suggested_rewrite가 비어 있으면, 아래 내용을 포함하는 추가 문안을 자동 생성:
  - 해지 요건을 “객관적으로 중대하고 회복 곤란한 위반”으로 한정
  - 원칙: 서면 최고 + 상당한 시정기간(예: 15일 이상)
  - 예외: 즉시 해지 가능한 사유를 좁게 열거
  - 해지 시 정산/자료 반환 등 후속 절차 명확화
- risk_tier를 HIGH로 승격(필수 검토 대상으로 상단 노출)
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 2) 제21조(불공정행위 금지) redline candidate 강제 생성
- suggested_rewrite가 비어 있으면, 아래 내용을 포함하는 추가 문안을 자동 생성:
  - 불이익 제공/지위 남용 금지 의무를 구체화
  - 비용부담/공제/상계는 사전 서면합의 + 항목·기준·증빙 요건화
  - 정산자료 제공/확인권(자료 제공 협조) 명문화
- risk_tier를 HIGH로 승격(대리점법 핵심 조항으로 상단 노출)
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) 제14조(인력 채용/관리) 경영간섭 리스크 문안 생성
- 인사권(채용/배치/평가/징계) 자율성 보장
- 운영기준 제시와 직접 지시/강제의 경계를 명확화
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 4) 제11조/제17조 비용전가·비용분담 문안 생성
- 판촉/광고/반품/원상회복 등 비용 항목별 사전 서면합의
- 상한(캡)·증빙·이의제기 절차 포함
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 5) 제8~10조 정산/상계/공제 통제 문안 생성
- 공제/상계 요건을 계약/서면합의로 제한
- 정산서·증빙 제공 및 이의제기 절차 명문화
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## DOCX 출력 개선
- MEDIUM/LOW 조항에서도 “참고 문안(suggested_rewrite)”이 Word에 표시되도록 guidance 섹션에 문안 본문을 포함
- 구현: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

