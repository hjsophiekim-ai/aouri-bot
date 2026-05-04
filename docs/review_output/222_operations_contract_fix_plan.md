# 222. 운영대행/위탁운영/공간운영 계약 이해 개선 Fix Plan(적용 완료)

## 목표
1) 운영대행/위탁운영/공간운영/서비스위탁 계열로 정확히 분류(앱개발 오탐 방지)  
2) 사용자 입력 핵심 이슈를 review objective로 강제 반영  
3) 운영대행 계약에 맞는 질문만 생성(앱개발 질문 차단)  
4) 법령검색을 운영대행/대리점/하도급/산안/개인정보 중심으로 재설계  
5) UI 결과와 DOCX 결과를 단일 소스로 통합(불일치 시 실패 처리)  

## 적용 변경(핵심)
### A. 계약유형(contract_type) 분류 룰 개선
- 운영대행 전용 contract_type 추가:
  - `운영대행/위탁운영/공간운영/서비스위탁`
- 광고/마케팅 분류의 `대행`을 “광고/마케팅/홍보 대행”으로 제한해 운영대행 오염 차단
- 구현:
  - [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py)
  - [infer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/infer.py)

### B. ContractProfile 신설: ops_outsourcing
- 운영대행 계약을 `ops_outsourcing`으로 분류:
  - 운영대행/위탁운영/시설관리/운영인력/보고/검수/정산/운영수수료/하도급/안전관리 신호 활용
  - app_dev는 소스코드/SOW/SBOM/오픈소스/API/개발 등 “강한 신호”에서만 우선
- 구현:
  - [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)

### C. user focus issue 강제 반영
- user_focus_hit 판정에 “topic 매핑 + keyword 매칭”을 모두 사용:
  - 조항 주제(topic)가 달라도, 사용자 objective 키워드가 조항 텍스트에 있으면 hit로 처리
- 또한 dealer 불공정 objective는 termination/dispute에도 매핑 확장
- 구현:
  - [user_focus.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/user_focus.py)
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### D. 질문 엔진: 운영대행 전용 질문 세트
- `ops_outsourcing` 프로파일이면 운영대행 전용 질문(최대 5개)만 생성:
  - 상대방 양식
  - 운영범위/KPI/보고·검수
  - 인력배치/교체/지휘감독
  - 정산(산식/주기/증빙/이의)
  - 하도급/재위탁 통제(사전승인/책임)
  - (조건부) 안전/개인정보/해지 인수인계
  - (user_focus 있을 때) 불이익/경영간섭/해지 남용 확인 질문 가중
- 구현:
  - [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)

### E. 법령검색: operations 프로파일 신설 및 저작권 편향 차단
- 운영대행 계약은 law profile을 `operations`로 분류
- allowlist를 공정거래/대리점/하도급/산안/개인정보/노무 중심으로 구성
- app_dev로 잘못 분류될 때만 저작권법이 과대표집되던 구조를 차단
- 구현:
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

### F. UI/Word 단일 소스(재확인)
- 세션에 original_clauses 저장 → DOCX 생성은 이를 우선 사용
- clause_id 누락/changed set 불일치(UI vs DOCX) 발생 시 DOCX 생성 실패 처리
- 구현:
  - [storage.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/storage.py)
  - [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## 검증
- 자동 테스트 추가/통과:
  - [test_operations_contract_flow.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_operations_contract_flow.py)
- 전체 테스트: `runtime/tests` 기준 통과(45 tests OK)

