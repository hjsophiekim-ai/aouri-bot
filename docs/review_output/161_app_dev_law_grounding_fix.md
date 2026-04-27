# 161. 앱 개발계약 전용 Law Grounding Fix(app_dev profile)

## 문제
- 앱 개발계약인데도 law_search가 표시광고/소비자보호/모델계약 같은 주제로 검색되는 경우가 있었다.
- 원인:
  - entity(특히 일룸)의 기본 우선 토픽에 광고/모델 관련이 포함되어 있고
  - contract_type 또는 본문 키워드에 “광고”가 섞이면 ads 토픽이 자동 확장되며
  - 계약 프로파일이 app dev로 인식되지 않으면 쿼리 템플릿이 앱 개발계약에 맞게 좁혀지지 않았다.

## 목표
- 앱 개발계약이면 표시광고/모델계약/소비자보호 토픽을 자동 억제
- 앱 개발계약 우선 법령군(민법/저작권/부정경쟁/개인정보/정보통신망 등) 중심으로 좁게 검색
- issue(rule_id)별 쿼리 템플릿을 제공
- 결과가 비면(리랭크로 모두 제거 등) 완화된 fallback을 적용

## 변경 파일
- app_dev 프로파일 및 쿼리 템플릿/억제/폴백:
  - [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
- entity 우선 토픽 정제(일룸의 광고/모델 토픽 제거 + app dev 토픽 보강):
  - [priority_rules.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/priority_rules.py)

## 핵심 구현 요약
### 1) 계약 프로파일(app_dev) 인식
- 텍스트/contract_type에 앱 개발, 소프트웨어 개발, SI, 유지보수, SaaS, API 연동, 소스코드, 산출물, SLA 등의 힌트가 있으면 `profile=app_dev`로 분류한다.
- 위치: [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

### 2) app_dev 기본 쿼리(우선 법령/법리)
- contract scope에서 app_dev면 아래를 우선 쿼리로 사용:
  - 민법(도급/채무불이행/손해배상)
  - 저작권법(프로그램 저작권/양도)
  - 부정경쟁방지법(영업비밀/소스코드)
  - 개인정보보호법(유출/손해배상)
  - 전자상거래법(서비스 성격 강한 경우에 한해)

### 3) ads 토픽 자동 억제
- `profile=app_dev`인 경우:
  - contract_type/text 기반 “표시광고/소비자보호” 자동 쿼리를 추가하지 않는다.
- 위치: [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

### 4) 룰(APP-xxx)별 쿼리 템플릿
- APP-001/008(IP/제3자): 저작권법/권리침해 보증
- APP-002(OSS): 저작권법 라이선스 위반/오픈소스 의무
- APP-003~006/011/012(SOW/검수/지연/SLA/종료/성능): 민법 도급/채무불이행 중심
- APP-007/010(보안/개인정보/삭제): 개인정보보호법 + 정보통신망 침해사고

### 5) 결과가 비면 완화 fallback
- 리랭크 과정에서 모두 제거되어 빈 배열이 되는 경우를 대비해, 노이즈(입법예고/조례안/공고 등)만 제거한 뒤 점수 완화로 상위 항목을 반환한다.

