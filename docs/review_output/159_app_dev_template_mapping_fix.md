# 159. 앱 개발계약 템플릿 매핑/분류 보강

## 목표
- 앱 개발계약서/소프트웨어 개발계약서/SI/유지보수/SaaS/API 연동 계약을 contract_type으로 인식
- `suggested_template_ids=[]`로 끝나지 않도록 템플릿 추천을 보강
- 단일 템플릿(예: “영문 디자인용역 계약서”)로만 고정하지 않고, 개발계약 핵심 쟁점(산출물/IP, OSS, SLA, 개인정보, 보안, 전환/인수인계)을 커버할 조합을 기본 제공

## 변경 사항
### 1) contract_type 분류(app dev) 추가
- 파일: [classify.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/classify.py)
- 추가된 계약유형:
  - `앱개발/소프트웨어개발/SI/유지보수/SaaS`
- 반영 키워드(예시):
  - 앱 개발, 소프트웨어 개발, 시스템 개발, 개발용역, IT 용역, SI, 유지보수, SaaS, API 연동, 소스코드, 산출물 등

### 2) 텍스트 기반 contract_type 확장(app dev) 추가
- 파일: [query_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)
- 사용자가 contract_type을 잘못 넣거나 “기타/미분류”로 떨어져도, 본문에 app dev 힌트가 있으면 `앱개발/소프트웨어개발/SI/유지보수/SaaS`를 추가 적용하여 룰이 붙도록 보강

### 3) 템플릿 추천(app dev) 강화 + fallback 전략
- 파일: [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
- app dev 키워드 매핑 추가
- 후보가 빈 배열로 끝나면, 아래 조합을 우선 보강:
  - 용역(가장 가까운 용역 템플릿)
  - 개인정보/DPA
  - 라이선스/로열티
  - NDA
- 그래도 비어 있으면(템플릿 폴더 상태에 따라) supported 템플릿 1개를 최소 반환

## 기대 효과
- 앱 개발계약 입력 시:
  - contract_type 인식이 안정화되어 룰/법령/질문/수정제안의 기반이 살아남
  - 초안 화면에서 suggested_template_ids가 빈 배열로 끝나지 않아, “용역+개인정보+라이선스(+NDA)” 조합으로 작업 시작 가능

