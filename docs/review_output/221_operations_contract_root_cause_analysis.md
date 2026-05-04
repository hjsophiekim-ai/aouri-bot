# 221. (데스커 라운지 대구) 운영대행 계약 오탐/오염 Root Cause 분석

## 관찰된 증상(요약)
- 계약 핵심은 공간 운영/인력 배치/보고·자료제출/검수/정산/하도급 승인/안전관리/기밀/해지 등인데,
  - 앱개발 계약처럼 IP/오픈소스/SOW/SLA 질문·법령으로 흐름
  - 사용자 입력 중점 이슈(불이익 제공/거래상 지위 남용/경영간섭/해지 남용)가 “탐지 없음”
  - UI와 Word 결과 불일치
  - 관련 법령이 저작권법 위주로 편향

## Root Cause 1) 계약유형(contract_type) 분류 규칙의 “대행” 오염
- [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py)에서 광고/마케팅 분류에 `대행`이 너무 일반적으로 포함되어 있어,
  - “운영대행”이 광고/마케팅으로 오분류될 가능성이 있었다.
- 조치: 운영대행을 별도 계약유형으로 분리하고, 마케팅 대행은 “광고/마케팅/홍보 대행”으로 제한.

## Root Cause 2) ContractProfile 추론(infer_contract_profile)의 오탐 구조
- [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)에서
  - `위탁` 같은 넓은 토큰으로 dealer로 떨어질 수 있고,
  - `유지보수/SLA` 같은 단어가 있을 때 app_dev로 오분류될 여지가 있었다(운영/서비스 계약에도 SLA라는 표현이 등장 가능).
- 조치: “운영대행/위탁운영/공간운영”을 별도 profile(`ops_outsourcing`)로 추가하고,
  - app_dev는 “소스코드/SOW/SBOM/오픈소스/API/개발” 등 강한 신호가 있을 때만 우선하도록 변경.

## Root Cause 3) user focus issue 탐지 로직이 topic 매핑에 과의존
- 조항별 user focus hit는 주로 “objective → clause_topic” 매핑에 의해 결정된다.
- 운영대행 계약에서 “경영간섭/지위 남용/해지 남용”은
  - 운영지침/평가/제재/해지/정산/보고 조항에 흩어져 나타나며,
  - 항상 `dealer_unfair` topic으로 분류되지 않아 “탐지 없음”으로 떨어질 수 있었다.
- 조치: user focus objective의 키워드를 조항 텍스트에 직접 매칭하는 “keyword hit”를 추가해 강제 반영.

## Root Cause 4) 법령검색 프로파일이 app_dev로 기울면 저작권법이 과대표집
- 법령검색은 별도 프로파일 추론을 사용하며([search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)),
  - app_dev로 분류되면 allowlist에 저작권법이 포함되어 결과가 저작권 중심으로 재정렬될 수 있다.
- 조치: 운영대행 프로파일(`operations`)을 신설하고 allowlist를
  - 대리점/공정거래/하도급/산안/개인정보/노무 중심으로 재구성.

## Root Cause 5) UI/Word 불일치는 “서로 다른 clause set” 사용 시 발생
- 세션 기반 결과와 원문 재추출 결과가 분기되면 clause_id 집합이 달라질 수 있다.
- 조치: 세션에 original_clauses를 저장하고 docx 생성은 이를 우선 사용하며,
  - clause_id 누락/changed set 불일치 시 docx 생성 자체를 실패 처리하도록 가드레일을 둠.

