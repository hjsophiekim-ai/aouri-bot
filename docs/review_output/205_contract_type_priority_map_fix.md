# 205) 계약유형별 핵심 이슈 priority map 재설계/적용

## 목표

- 대리점/위탁거래 계약에서 앱개발/설치/현장안전 계열 이슈가 섞이지 않게 한다.
- 계약유형별로 “진짜 중요한 쟁점”을 우선순위로 잡아 검토/질문/수정제안을 안정화한다.

## 구현

### 1) 계약 프로파일(ContractProfile) 도입

- 계약유형 문자열 + 본문 키워드 기반으로 프로파일을 추론한다.
  - `dealer_consignment`
  - `app_dev`
  - `onsite_installation`
  - `privacy_dpa`
  - `generic`
- 위치: [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)

### 2) 프로파일별 핵심 이슈(우선순위) 정의

- 대리점/위탁거래(priority 예시)
  - 비용전가/판촉·광고·반품비
  - 정산/상계/공제
  - 해지/불이익 조치
  - 분쟁해결(국내 기준)
  - 개인정보(있는 경우만)
- 앱개발(priority 예시)
  - SOW/변경관리, IP, 오픈소스, 검수, SLA/보안/개인정보, 종료/인수인계
- 설치/현장(priority 예시)
  - 안전관리/산안법/중대재해, 재위탁/하도급, 검수·시운전
- 개인정보 처리위탁(priority 예시)
  - 목적 외 이용 금지, 재위탁, 안전조치, 파기/반환, 침해사고 통지
- 위치: [priority_map.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/priority_map.py)

### 3) review meta에 프로파일 정보 포함

- 후속 단계(질문/표시/가드레일)에서 공통 사용 가능하도록 meta에 포함한다.
- 위치: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L856-L871)

