# 191) 법령 검색 정밀도 개선(난민법 등 무관 법령 제거)

## 문제

- 대리점 계약/앱 개발계약 결과에서 **난민법** 등 계약과 무관한 법령이 `related_laws`에 섞여 표시되는 사례가 발생.
- 원인(핵심):
  - law target에 가중치(+2)가 들어가면서 **문맥 토큰 오버랩이 0이어도** “법령”이면 상위로 올라올 수 있었음.
  - 계약유형별 “허용 법령군” 제약이 없어, 검색 결과의 노이즈가 그대로 남는 구조였음.

## 해결

### 1) contract profile 확장

- `contract_type`/`text`에서 대리점/유통 시그널을 감지해 `profile="dealer"`로 분류.

### 2) 계약유형별 허용 법령군(allowlist) 도입 + 강제 제외(ban) 도입

- profile별 allowlist에 포함되지 않는 법령명은 최종 결과에서 제거.
- 난민법/난민법 시행령/시행규칙은 profile과 무관하게 항상 제외(무관 법령이 “절대 나오지 않게”).

### 3) rerank 필터 기준을 “score”가 아니라 “문맥 오버랩” 기반으로 강화

- `law`는 allowlist 기반으로 통과시키되,
- `prec/expc`(판례/해석례)는 오버랩이 낮으면 제외(직접 관련성 낮은 제목 제거 강화).

## 변경 파일

- [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)
  - `_infer_contract_profile()`에 `dealer` 추가
  - `_allowed_law_keywords_by_profile()` allowlist 추가
  - `_BANNED_ALWAYS_TITLES`(난민법 계열) 추가
  - `_rerank_and_filter_references(..., profile=...)`로 필터 로직 강화
  - `_search_target()`에서 profile 전달 및 검색 display 확장(후보 풀을 늘려 정밀 rerank 가능)

## 기대 효과

- 대리점 계약에서 **대리점법/공정거래법/민법/상법** 중심으로 안정적으로 수렴.
- 난민법 등 무관 법령이 결과 화면/Word 부록에 포함되는 현상 차단.

