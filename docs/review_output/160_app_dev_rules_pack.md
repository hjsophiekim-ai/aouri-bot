# 160. 앱 개발계약 Rule 세트 보강(APP-001~APP-012)

## 목표
- 앱 개발계약서/소프트웨어 개발계약서/SI/유지보수/SaaS/API 연동 계약에서 `issues=0`으로 끝나지 않도록 핵심 이슈를 트리거 기반으로 탐지
- 기존 rules json/loader/query service 와 호환되게 추가
- clause-level revision(조항별 수정제안)까지 이어지도록 rule_id 기반 deterministic rewrite fallback을 일부 제공

## 변경 파일
- 룰 추가: [review_rules_master.json](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/resources/review_rules_master.json)
- clause-level 리라이트(일부 APP 룰): [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)
- 텍스트 기반 contract_type 확장(app dev): [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)

## 추가된 룰 목록(요약)
- APP-001: 산출물/소스코드/IP 귀속 및 사용권 점검
- APP-002: 오픈소스 사용/라이선스 위반 리스크 점검
- APP-003: 개발 범위/사양(SOW) 불명확 리스크 점검
- APP-004: 검수 기준/기간/간주검수 및 재검수 점검
- APP-005: 마일스톤 지연/지연손해금(지체상금) 점검
- APP-006: 하자보수/유지보수/SLA 및 장애 대응 점검
- APP-007: 보안사고/개인정보 유출 책임 및 통지/대응 점검
- APP-008: 제3자 솔루션/라이브러리 사용 및 권리침해 보증 점검
- APP-009: 재위탁/하도급 개발 제한 및 승인 점검
- APP-010: 데이터 이전/반환/삭제 및 로그/백업 처리 점검
- APP-011: 계약 종료 시 인수인계/소스코드 이전/전환 협력 점검
- APP-012: 성능보장/가용성/서비스 수준 점검

## 트리거 설계(issues=0 방지)
- 모든 APP 룰은 `tags`에 `trigger:*`를 포함해 본문 키워드 매칭으로 `matched_rules`에 올라오도록 구성했다.
- 특히 APP-003에는 `trigger:개발`을 추가하여 앱 개발계약에서 최소 1개 이상 매칭될 가능성을 높였다.
- 적용 대상 contract_type은 주로 `앱개발/소프트웨어개발/SI/유지보수/SaaS`(+ 필요시 용역/라이선스/DPA)에 연결했다.

## clause-level rewrite 보강(요약)
- 일부 APP 룰에 대해 deterministic rewrite를 추가하여, AI 비활성 상태에서도 “조항별 수정 제안”이 비지 않도록 했다.
- 매핑(현재 구현):
  - APP-001, APP-002, APP-003, APP-004, APP-006, APP-007, APP-009, APP-010, APP-011
- 구현 위치: [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

