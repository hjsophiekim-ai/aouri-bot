# 국가법령정보 Open API 환경변수 설정 (LAW_API_*)

가이드에서 인증값은 요청 파라미터 `OC`로 전달되며, aouribot에서는 이를 `LAW_API_KEY`로 관리합니다. (출처: guideResult 요청변수 표)

---

## 1) .env.example 반영 내용

- 파일: [.env.example](file:///c:/Users/FURSYS/Desktop/aouribot/.env.example)
- 추가된 항목:
  - `LAW_API_ENABLED=false`
  - `LAW_API_KEY=`
  - `LAW_API_BASE_URL=https://www.law.go.kr/DRF`
  - `LAW_API_TIMEOUT=20`
  - `LAW_API_RETRY=2`

---

## 2) config 로더

- 파일: [config.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/config.py)
- 동작:
  - `LAW_API_KEY`가 환경변수에 없으면 `.env/.env.local/docs/.env/docs/.env.local` 순으로 로딩 시도(override=false)
  - `LAW_API_ENABLED=true` + `LAW_API_KEY`가 있어야만 `enabled=true`
  - 키가 없으면 자동으로 `enabled=false`로 강등

---

## 3) 키가 없을 때 graceful fallback

- `/api/review/analyze`, `/api/questions/generate`, `/api/revision/suggest_text`는
  - 키가 없거나 `LAW_API_ENABLED=false`면 호출을 시도하지 않고,
  - 응답의 `law_search.enabled=false`로 반환합니다.

---

## 4) 주의사항

- `LAW_API_KEY`는 절대 코드/로그/문서에 직접 입력하지 마세요.
- DRF(Open API) 호출 실패 메시지에서 “IP주소 및 도메인주소 등록”이 요구될 수 있으므로,
  - 키 발급 후 운영 서버(또는 개발 서버)의 IP/도메인을 등록해야 실제 호출이 성공합니다.

