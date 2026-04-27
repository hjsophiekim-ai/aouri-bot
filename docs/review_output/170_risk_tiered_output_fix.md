# 170. Risk tier 정책 적용(HIGH=redline, MEDIUM=guidance, LOW=참고/숨김)

## 문제
- 현재 결과가 “거의 모든 수정 제안이 HIGH”처럼 보이며,
  - 앱 화면도 대부분 빨간 수정 대상으로 보이는 인상이 강했다.

## 목표
1) HIGH만 redline 필수 수정  
2) MEDIUM은 blue suggestion(방향 제안)  
3) LOW는 참고 메모 또는 숨김 가능  
4) “꼭 수정할 조항”과 “보완하면 좋은 조항” 분리  
5) 결과 화면 상단에 필수/권장/참고 개수 표시  
6) Word도 본문 redline / 부록 guidance 섹션으로 분리  

## 변경 사항
### 1) APP-xxx 룰의 risk_level 재조정(과도 HIGH 완화)
- 파일: [review_rules_master.json](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/resources/review_rules_master.json)
- 조정 예시:
  - APP-003(SOW), APP-006(유지보수/SLA), APP-009(재위탁), APP-010(데이터), APP-011(인수인계) → `MEDIUM`
  - SOW는 `trigger:개발`을 제거하여 “모든 조항이 매칭되는” 과매칭을 완화

### 2) API 결과에 risk_tier 포함 및 tier_counts 제공
- 파일: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- `clause_results[]`에 `risk_tier(HIGH/MEDIUM/LOW)` 포함
- `clause_meta.tier_counts`에 `{ must, medium, low }` 제공
- 정렬도 HIGH → MEDIUM → LOW 순으로 변경

### 3) 앱 화면: HIGH만 redline, MEDIUM/LOW는 guidance
- 파일: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- 상단 메타에 `필수수정/권장/참고` 카운트 표시
- 조항 카드:
  - `HIGH/승인필요`만 diff 기반 redline(추가=빨강, 삭제=빨강+취소선)
  - 그 외는 파란 guidance 박스로 “방향/사유/참고 문안” 표시
  - LOW는 기본 리스트에서 숨김(필요 시 확장 가능)

### 4) Word: redline(필수) / guidance(권장/참고) 분리
- 파일: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- 본문 redline 섹션은 `HIGH`만 출력
- `MEDIUM/LOW`는 파란색 guidance 섹션으로 분리 출력
- 부록 표는 “수정 전/후 핵심 표현” 기반으로 자연어 가독성 개선(168 연동)

## 기대 효과
- 화면/Word에서 “반드시 고쳐야 하는 조항”과 “보완 권고”가 명확히 분리된다.
- 과도한 전체 redline 인상을 줄이고, 법무팀이 읽기 쉬운 산출물로 정리된다.

