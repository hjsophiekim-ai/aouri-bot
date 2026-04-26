# .env 형식 자동 점검(117)

## 1) .env 파일 존재 여부
- `.env` exists: `true`
- `.env.local` exists: `false`

## 2)~5) 키 라인/값 점검(값 미출력)
- `OPENAI_API_KEY` in .env: line_present=`true`, value_nonempty=`true`
- `LAW_API_KEY` in .env: line_present=`true`, value_nonempty=`true`
- `LAW_API_ENABLED` in .env: line_present=`true`, value_nonempty=`true`

## 형식/인코딩 이슈 점검
- .env utf-8 decode ok: `true`
- .env BOM detected: `true`
- .env line endings: `lf`
- OPENAI_API_KEY key has leading BOM: `false`
- LAW_API_KEY key has leading BOM: `false`
- OPENAI_API_KEY has quotes: `false` / has inline comment: `false`
- LAW_API_KEY has quotes: `false` / has inline comment: `false`

## 자동 수정 제안(값은 예시로만 표기)
- 파일 시작에 BOM이 있으면 제거(UTF-8 without BOM 저장 권장)
- 키 라인을 아래 형태로 맞추기(공백 최소화)
  - `OPENAI_API_KEY=<YOUR_KEY>`
  - `LAW_API_ENABLED=true`
  - `LAW_API_KEY=<YOUR_KEY>`

