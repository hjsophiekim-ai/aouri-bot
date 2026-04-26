# 국가법령정보 Open API(DRF) 런타임 호출 검증

## 확인 항목
- LAW_API_ENABLED=true 여부
- LAW_API_KEY 적용 여부(값 미출력)
- 샘플 키워드로 법령 검색 성공 여부
- 샘플 키워드로 판례 검색 성공 여부
- 응답 형식(JSON) 파싱 성공 여부
- timeout / 인증오류 / IP제한 여부
- 실패 시 원인 상세

## 런타임 설정 인식
- LAW_API_ENABLED(효과): `true`
- LAW_API_KEY(존재): `true`
- base_url: `https://www.law.go.kr/DRF`
- timeout_sec: `30.0` / retry_count: `2`

## 1) 법령 검색 (target=law)
- ok: `true`
- elapsed_client_sec: `0.5589`
- parse_ok: `true`
- item_count_guess: `2`

## 2) 판례 검색 (target=prec)
- ok: `true`
- elapsed_client_sec: `0.2978`
- parse_ok: `true`
- item_count_guess: `0`

## 판정/해석
- 키 값(OC)은 출력하지 않으며, 실패 시에도 원인만 기록했다.

