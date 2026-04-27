# 156. 앱 개발계약 검토 불능 Root Cause Analysis (코드 기준)

## 결론 요약
- 앱 개발계약서(앱/소프트웨어 개발, SI, 유지보수, SaaS, API 연동)는 기존 분류/룰/법령/질문/리라이트 체계에서 “탐지 트리거”와 “우선 법령 프로파일”이 거의 없어 `issues=0`으로 수렴했다.
- 동시에 `/api/review/analyze`는 AI provider를 생성해놓고도 clause-level 엔진에 전달하지 않아, 조항별 수정문안 품질이 AI 없이 동작했다.

## 1) `/api/review/analyze`에서 AI를 생성해도 실제 검토 엔진에 사용되지 않음
- 위치: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- 문제 흐름(수정 전):
  - `ai_provider`를 생성해도 `build_clause_level_result(..., ai_provider=None, ai_model=None, ...)`로 호출되어 clause-level rewrite/이유 생성에 AI가 개입할 수 없었다.
- 영향:
  - 앱 개발계약서처럼 조항 문구가 다양하고 “정밀 문장 리라이트”가 중요한 계약에서, deterministic fallback만으로는 실무 수준 수정문안을 만들기 어렵다.

## 2) 앱 개발계약 contract_type 인식 부재 → 룰/템플릿/법령 매핑 붕괴
- 분류기(계약유형) 미인식:
  - 기존 `CONTRACT_TYPE_RULES`에 앱 개발계약군 키워드가 없어 텍스트/파일명 기반 분류가 `기타/미분류`로 떨어질 가능성이 높았다.
  - 위치: [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py)
- 템플릿 추천 실패:
  - `suggest_template_ids()`는 힌트 테이블이 제한적이라 앱 개발계약에서 `suggested_template_ids=[]`로 끝나기 쉬웠다.
  - 위치: [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
- 결과:
  - 룰 적용 범위가 좁아져 `matched_rules`가 빈 상태로 시작 → clause-level revision 항목도 생성되지 않음 → 질문/법령/수정제안이 연쇄적으로 빈 결과를 낳음.

## 3) 질문 엔진의 “앱 개발계약 특화” 부족 (clause-aware 보강 미흡)
- 질문 생성은 `detected_rule_ids`, `law_topics`, `contract_text`, `clause_results`를 기반으로 후보를 구성한다.
- 앱 개발계약에 대한 특화 질문(산출물/IP, 오픈소스, SOW, 검수, SLA, 보안사고, 종료/전환)이 부족하면:
  - 사용자 답변으로 확장되는 contract_type/룰 적용이 발생하지 않고
  - clause-aware 보강 질문도 생성되지 않아 검토 깊이가 올라가지 않는다.
- 위치: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)

## 4) Draft 엔진은 “템플릿 텍스트 + 룰 제안” 중심으로 설계되어 있었음(표현상/구조상)
- Draft 생성은 기본적으로 템플릿 텍스트를 기반으로 하고, 룰을 suggestion으로 덧붙이는 구조다.
- 서버 레벨에서 AI 문구 보강은 존재하지만, 템플릿 추천이 실패하면 애초에 초안/검토 흐름이 끊긴다.
- 위치:
  - 템플릿 기반 draft 생성: [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
  - AI 문구 보강 적용: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

## “issues=0”으로 끝난 직접 원인(요약)
- 분류 미인식(기타/미분류) + 앱 개발계약 룰 트리거 부재 → `matched_rules`가 비어 revision 대상 조항이 만들어지지 않음.
- law_search는 우선순위 토픽(예: 표시광고/모델계약 등)이나 텍스트 키워드에 끌려가 앱 개발계약과 맞지 않는 결과가 섞이거나 비게 됨.

