# /demo 아우리봇 이미지 정적 서빙(/static) 처리

## 목표
- `/demo`에서 `docs/아우리봇.png`가 깨지지 않도록 안정적으로 표시
- runtime 기준 정적 리소스 경로를 확정하고, EP 연동 시에도 재사용 가능한 형태로 제공

## 최종 URL
- 이미지 URL: `http://127.0.0.1:8787/static/aouribot.png`

## 서버 구현 방식(MVP)
### 1) 경로 설계
- `/static/<key>` 형태의 정적 리소스 라우트를 제공
- 파일 시스템 경로는 “화이트리스트 매핑(static_map)”으로만 결정(경로 탐색 공격 방지)

### 2) 실제 파일 소스
- 소스 파일: `docs/아우리봇.png`
- 런타임은 repo root 기준으로 파일을 직접 읽어서 서빙한다(별도 복사 없이 동작).

## 구현 파일(실제 코드)
- 라우팅/서빙: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - `REPO_ROOT` 기반 경로 계산
  - `static_map = { "aouribot.png": REPO_ROOT / "docs" / "아우리봇.png" }`
  - `GET /static/aouribot.png` 처리
  - `_static_response()`에서 Content-Type 자동 설정(png/jpg/svg/css/js)

## 데모 UI 연결
- [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py)
  - `<img src="/static/aouribot.png" ...>`
  - favicon / apple-touch-icon도 동일 이미지 사용

## 검증 방법
PowerShell:
```powershell
$base='http://127.0.0.1:8787'
Invoke-WebRequest "$base/static/aouribot.png" -UseBasicParsing | Select-Object StatusCode, Headers, RawContentLength
```

기대:
- HTTP 200
- `Content-Type: image/png`

## 운영상 주의
- 현재 이미지 파일은 크기가 큼(약 5.7MB). 데모에는 문제 없지만 EP 탑재 전에는 최적화(리사이즈/압축) 권장.

