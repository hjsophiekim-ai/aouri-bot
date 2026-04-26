# 국가법령정보 Open API(DRF) 런타임 호출 재검증(104)

## 런타임 설정 인식(값 미노출)
- enabled: `true`
- api_key_present: `true`
- base_url: `https://www.law.go.kr/DRF`

## 1) 법령 검색 (target=law)
- {"ok": true, "elapsed_client_sec": 0.3109, "parse_ok": true, "item_count_guess": 2}

## 2) 판례 검색 (target=prec)
- {"ok": true, "elapsed_client_sec": 0.2885, "parse_ok": true, "item_count_guess": 0}

