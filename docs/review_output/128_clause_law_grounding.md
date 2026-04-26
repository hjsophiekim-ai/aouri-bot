# 128. Clause별 Law Grounding 연결

## 목표
- law_search가 “전체 결과 패널”에 머무르지 않고, **각 조항의 수정 제안과 직접 연결**되도록 구성
- 조항마다 “왜 문제인지”를 법령/판례/해석례 제목/링크 기준으로 설명 가능하게 만들기

## 구현 개요
- 법령 검색 서비스: [search_service.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
- 조항별 결과에 `related_laws` 필드를 채우는 로직: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 동작 방식
1) 문서 전체에서 룰 매칭 및 조항 분해 수행
2) 이슈가 있는 조항(`clause_results`)에 대해, 각 조항의 `original_text`와 `related_rules`를 입력으로 DRF 검색 호출
3) 결과를 `clause_results[i].related_laws`에 저장

## 검색 정교화 포인트(현재)
- contract_type 및 clause 텍스트 기반 토픽 파생: `_derive_topics()` ([search_service.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/law/search_service.py))
- 룰 기반 토픽 보강 예시:
  - 대리점/비용전가: `RISK-006` → 대리점법/공정거래
  - 하도급/기술자료/단가감액: `RISK-004`, `RISK-005` → 하도급법
  - 안전/중대재해: `RISK-003` → 산안법/중대재해처벌법

## 성능/안정성 제약
- clause별 law_search는 비용이 크므로, 이슈 조항 상위 N개만 수행(현재 최대 10개)
- 각 target(law/prec/expc)별 max_per_type를 제한(현재 2개)
- 캐시(JsonFileCache) 기반으로 동일 query 반복 호출을 줄임

## 결과 연결
- 각 조항의 `rewrite_reason`에 `related_laws`의 대표 제목을 포함해 “근거가 있는 설명”으로 결합
- docx 생성 시에도 조항별 “관련 법령/판례” 섹션으로 함께 기록
