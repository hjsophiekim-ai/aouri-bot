# 국가법령정보 Open API(DRF) Endpoint 점검/교정(96)

## 결론
- DRF 베이스 URL은 `https://www.law.go.kr/DRF`가 맞다.
- 런타임에서 `LAW_API_BASE_URL`이 `https://open.law.go.kr`로 설정되면 DRF 엔드포인트(`/DRF/lawSearch.do`, `/DRF/lawService.do`)가 존재하지 않아 HTTP 404가 발생한다.
- 코드에서 `LAW_API_BASE_URL`을 정규화해(가이드 기준) `open.law.go.kr`이 들어오면 자동으로 `https://www.law.go.kr/DRF`로 교정하도록 수정했다.

## 가이드 기준 엔드포인트(코드 구현과 일치)
- 검색(목록): `GET {BASE}/lawSearch.do?OC=...&target=...&type=JSON&query=...`
- 상세(본문): `GET {BASE}/lawService.do?OC=...&target=...&type=...`
- 런타임 구현: [drf_client.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/drf_client.py#L33-L112)

## 404 원인(코드/설정 기준)
- `LAW_API_BASE_URL` 값이 `open.law.go.kr`(가이드/문서 페이지 도메인)로 들어오면, DRF 호출은 `open.law.go.kr/DRF/lawSearch.do` 형태가 되어 404가 발생한다.
- 해당 값은 [load_law_api_config()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/config.py#L50-L92)에서 환경변수 `LAW_API_BASE_URL`을 그대로 사용하기 때문에 발생했다.

## 적용한 교정
- `LAW_API_BASE_URL`이 아래 형태로 들어오면 자동 교정
  - `open.law.go.kr` 포함 → `https://www.law.go.kr/DRF`로 강제
  - `law.go.kr` 도메인이지만 `/DRF`가 없으면 `/DRF` 자동 부착
- 변경 코드: [load_law_api_config()](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/config.py#L50-L92)

## 재검증(요약)
- 교정 후 base_url이 `https://www.law.go.kr/DRF`로 인식됨: [102_env_runtime_validation_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/102_env_runtime_validation_rerun.md)
- DRF 직접 호출 성공(법령 검색): [104_law_api_runtime_check_rerun.md](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/docs/review_output/104_law_api_runtime_check_rerun.md)
