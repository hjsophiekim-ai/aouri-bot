# 16. entity / contract_type 1차 추정(운영 편의 우선) 구현

## 1) 목표
- 업로드/배치 실행 시 사용자가 `entity`, `contract_type`을 입력하지 않아도
  - 파일명/경로/기존 분류 결과(캐시/메타)를 기반으로 1차 추정을 수행한다.
- 정확도보다 운영 편의 우선
- 추정값은 항상 “추정”으로 표시하고, 사용자가 언제든 수동 변경 가능해야 한다.

## 2) 적용 범위
- Upload 흐름: `POST /api/upload`
- Batch Review 흐름: `scripts/run_batch_review.py`

## 3) 구현 코드
- 추정 모듈: `aouri-bot/runtime/review/infer.py`
  - 추정 소스 우선순위(사용자 입력이 없을 때):
    1. 캐시(`runtime/data/classification_cache.json`)
    2. 기존 분류 결과 메타(있으면) `docs/review_output/02_verified_meta.json`
    3. 파일명/경로 키워드 기반(`inferred_path`)
    4. 텍스트 기반 휴리스틱(`heuristic_text`)
- 분류 통합: `aouri-bot/runtime/review/classify.py`
  - 반환값에 `is_inferred` 포함

## 4) 표시/수정 정책
- API 응답에 `classification.is_inferred=true|false` 포함
- 업로드 화면에서 사용자가 직접 입력(override) 가능
  - 사용자가 입력하면 `*_source=user_input`으로 기록

## 5) 캐시
- 경로: `aouri-bot/runtime/data/classification_cache.json`
- 목적: 자주 처리되는 파일명에 대해 운영 편의상 “최근 추정값”을 재사용
- 주의: 캐시는 “정답”이 아니라 운영 편의용이므로, 잘못 추정되면 UI에서 수정 후 재실행한다.

