# 176) Clause-specific 법령 retrieval 고도화

## 문제(기존)
- `LawSearchService.search_for_review()`가 실제 DRF를 호출하지만, 클라이언트 timeout이 `min(timeout, 1.5)`로 강제되어 clause-specific grounding이 얕아짐
- query template이 contract profile 중심이라, “조항 내용/이슈 타입/당사자 방향”을 충분히 반영하지 못함
- clause scope에서 precedents를 비활성화하는 경로가 있어(결과 다양성 저하) 실무형 근거(판례/해석례) 연결이 약함
- 결과가 비면 대체 질의(fallback) 캐스케이드가 약함

## 목표(적용)
- contract-level search와 clause-level search를 분리(호출 스코프 유지)
- high/medium(또는 must_fix) 조항 중심으로 clause별 개별 질의 생성
- 계약유형(profile) + 조항 내용 + 규칙(rule_id) + review_posture를 질의에 반영
- laws/precedents/interpretations 각각 rerank + 노이즈 필터 적용
- 결과가 비면 fallback query cascade 실행
- DRF detail URL(drf_detail_url)을 결과에 유지해 “근거 클릭” 가능한 형태로 제공

## 변경 사항(코드)
- DRF 클라이언트 timeout/retry 상향(과도한 1.5초 cap 제거):
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L27-L36)
- clause scope에서도 precedents/interpretations 검색 수행:
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L74-L110)
- clause-specific query 생성(토픽/프로필/룰/포스처 반영):
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L242-L466)
- clause 결과가 비면 fallback query cascade 재시도:
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py#L98-L110)
- clause-level grounding 적용 범위를 HIGH/MEDIUM 중심으로 확대 + context 전달:
  - [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L362-L381)

## 기대 효과
- “조항별 이슈 → 관련 법령/판례/해석례” 연결이 더 안정적으로 생성
- 결과가 비어있는 케이스에서 fallback 검색으로 최소 1~3개 근거 확보 확률 상승
- review_posture/role 기반으로 “우리에게 불리한 구조”를 더 정확히 잡아내는 grounding 기반 강화

