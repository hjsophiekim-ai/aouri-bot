# 157. 앱 개발계약 엔진 Fix Plan

## 목표
- 앱 개발계약서/소프트웨어 개발계약서/SI/유지보수/SaaS/API 연동 계약을 자동 인식한다.
- `/api/review/analyze`에서 실제 AI rewrite를 clause-level 엔진에 적용한다.
- 국가법령정보 API 조회가 앱 개발계약 이슈에 맞게 좁고 정확하게 동작한다.
- 검토 결과가 `issues=0`으로 끝나지 않도록 핵심 이슈를 탐지한다.
- 조항별 수정 제안과 DOCX redline 출력까지 이어지는 파이프라인을 유지한다.

## 변경 범위(파일)
- AI 적용 버그 수정: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- 계약유형 인식(app dev): [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py), [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)
- 템플릿 추천(app dev fallback): [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
- 앱 개발계약 룰 팩: [review_rules_master.json](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/resources/review_rules_master.json)
- 앱 개발계약 clause rewrite fallback: [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)
- 질문 엔진(app dev clause-aware): [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
- 법령 grounding(app dev profile): [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py), [priority_rules.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/priority_rules.py)

## 구현 계획(체크포인트)
### 1) Review Analyze 경로에 AI 적용(회귀 위험 낮음)
- `/api/review/analyze`에서도 `build_clause_level_result`에 `ai_provider/cfg.model/timeout/max_tokens/temperature`를 전달한다.
- 응답 `ai.enabled`가 “키 존재+openai provider 활성”과 일치하도록 하고, `ai.used`로 실제 clause-level 적용 여부를 분리한다.

### 2) 앱 개발계약 인식 강화(분류 + 텍스트 기반 확장)
- 텍스트/파일명에서 앱 개발계약 키워드를 잡아 contract_type을 `앱개발/소프트웨어개발/SI/유지보수/SaaS`로 분류한다.
- review analyze 단계에서 contract_type이 불명확해도 텍스트에서 contract_type을 추가 확장하여 룰이 붙도록 한다.

### 3) 템플릿 추천 로직 개선(빈 배열 방지)
- 앱 개발계약 키워드에 대해 단일 “디자인용역”으로만 매핑하지 않고, 용역+개인정보+DPA+라이선스(+NDA) 조합을 기본 추천으로 만든다.
- 후보가 전혀 없을 때도 최소 1개는 반환하도록 fallback 한다.

### 4) 앱 개발계약 룰 팩 추가(issues=0 방지)
- APP-001~APP-012 룰을 추가하여 핵심 이슈(산출물/IP, OSS, SOW, 검수, SLA, 보안, 재위탁, 데이터/종료/전환 등)를 트리거 기반으로 매칭한다.
- 최소 1개 룰은 “개발” 트리거를 포함해, 앱 개발계약에서 `matched_rules`가 0으로 끝나는 것을 방지한다.

### 5) 법령 grounding 프로파일(app_dev) 신설
- 앱 개발계약이면 표시광고/모델계약/소비자보호 토픽을 자동 억제한다(일룸 우선순위 토픽도 컨텍스트에 따라 정제).
- 민법(도급/채무불이행/손해배상), 저작권법, 부정경쟁방지법, 개인정보보호법을 기본 쿼리로 우선한다.
- 룰별(APP-xxx) 쿼리 템플릿을 추가하고, 리랭크 결과가 비면 완화된 fallback을 적용한다.

### 6) 질문 엔진(app dev) 보강
- 앱 개발계약이면 IP/OSS/SOW/검수·SLA/보안사고/데이터·전환 질문을 우선 생성한다(3~5개 상한 유지).
- 문서에 이미 있는 경우(키워드 존재) 질문을 억제한다.

## 검증 계획
- 단위테스트: `python -m unittest discover -s runtime/tests -p "test_*.py"` (repo의 [aouri-bot/](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot) 기준)
- API 정합성:
  - `/api/ai/health`의 enabled 값과
  - `/api/review/analyze` 응답의 `ai.enabled`
  - `/api/revision/suggest_text`의 `meta.ai` 존재 여부(사용/시도)를 비교
- 앱 개발계약 샘플 텍스트로:
  - contract_type이 app dev로 분류되는지
  - `matched_rules`가 APP-xxx를 포함하는지
  - law_search가 표시광고/모델계약으로 흐르지 않는지
  - clause_results에 suggested_rewrite가 생성되는지

