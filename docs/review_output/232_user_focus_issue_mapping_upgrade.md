# 232. 사용자 중점 이슈 매핑 업그레이드(대리점 계약 중심)

## 목표
- 사용자 입력 핵심 이슈를 “키워드만”으로 판단하지 않고, 의미적으로 관련된 조항에 강제 매핑
- 탐지 실패 시 “(탐지 없음)”으로 종료하지 않고 후보 조항과 원인(신호 약함)을 함께 표시

## 적용 변경
### 1) 대리점 계약: 조문 번호 기반 semantic 매핑 추가
- `dealer_consignment` 프로파일에서는 아래 조문 번호를 user_focus 강제 후보로 매핑:
  - 불이익 제공/지위 남용(`dealer_unfair_disadvantage`) → 제2, 제3, 제21, 제23
  - 경영간섭(`dealer_management_interference`) → 제5, 제14, 제18
  - 계약해지 남용(`termination_abuse`) → 제23, 제24
  - 비용전가(`dealer_cost_shift`) → 제11, 제17
  - 정산/상계(`settlement_offset`) → 제8~10
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 2) 키워드 히트 보강(기존 topic 매핑 + keyword 매칭)
- 조항 토픽(topic)이 달라도, objective 키워드가 조항 텍스트/제목/문맥에 존재하면 매핑 처리
- 구현: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

### 3) 탐지 실패 시 후보 조항/원인 표시
- `meta.user_focus_mapping_debug`에 objective별 매핑/후보/노트 제공
- UI 상단 “사용자 요청 핵심 이슈 반영 결과”에서
  - hits=0이면 후보 조항을 함께 노출
- 구현:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

## 기대 효과
- “관련 조항: (탐지 없음)”이 구조적으로 줄어들고, 실패하더라도 후보 조항이 표시되어 검토 흐름이 끊기지 않음
- 시디즈 대리점 계약의 제21/23/14/11/17/8~10이 user_focus와 안정적으로 연결됨

