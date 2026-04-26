# 129. AI Clause Rewrite Engine 연결

## 목표
- 판정은 rule + law_search 기반으로 유지
- OpenAI는 “조항별 수정문안 + 수정 이유”를 자연스럽게 작성하는 역할로 한정
- 근거 없는 자유 생성(환각) 금지
- 실패 시 fallback rewrite 사용

## 구현 위치
- 조항별 rewrite 적용: [clause_level.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

## 입력(모델에 전달되는 최소 단위)
각 조항에 대해 아래 정보를 JSON으로 전달합니다.
- `original_text` (원문 조항)
- `detected_issue_list` (검출 이슈)
- `related_rules` (적용 룰/근거 키워드 포함)
- `related_laws` (법령/판례/해석례 제목 및 detail URL)
- `fallback_rewrite` (룰 기반 fallback 수정문안)

## 출력(모델이 반환해야 하는 형태)
- JSON 배열
- 각 원소는 아래 키만 포함
  - `clause_id`
  - `rewrite_reason`
  - `suggested_rewrite`

## 안전장치(원칙)
- “판정”이나 “승인 필요 여부”는 모델이 바꾸지 않음(엔진이 이미 결정)
- 근거 없는 신규 의무/권리/법적 결론을 만들지 않도록 시스템 프롬프트에서 강제
- 모델이 JSON이 아닌 값을 반환하거나 실패하면:
  - 기존 `rewrite_reason`(룰+법령 제목 조합)
  - `suggested_rewrite`(fallback) 유지

## 호출 범위 제한
- 비용/지연을 줄이기 위해 조항별 rewrite는 상위 N개 조항만 수행(현재 기본 6개)
- 나머지는 룰 기반 fallback 수정문안으로 유지

## 기대 효과
- “위험” 표시에서 끝나지 않고, 조항별로 사람이 바로 복붙/반영할 수 있는 “추천 수정문안”을 생성
- law_search 결과(제목/링크)를 “수정 이유”에 결합해 설명 가능성 확보
