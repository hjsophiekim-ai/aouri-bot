# OpenAI API 키를 안전하게 로컬에 설정하는 방법(초보자용)

## 1) 새 키 발급 후 해야 할 일
- 키는 **비밀번호처럼 취급**한다(유출 시 즉시 폐기/재발급).
- 키를 메모장/문서/슬랙/채팅에 붙여넣지 않는다.
- Git 커밋/PR/이슈에 절대 올리지 않는다.

## 2) .env 파일 생성 방법
1) repo root의 `.env.example`을 복사해서 `.env`를 만든다.
2) `.env`의 `OPENAI_API_KEY`에 실제 키를 넣는다.
   - 예시(placeholder):
     - `OPENAI_API_KEY=YOUR_OPENAI_API_KEY`

파일 위치:
- `C:\\Users\\FURSYS\\Desktop\\aouribot\\.env`

## 3) placeholder 예시(절대 실제 키를 공유하지 말 것)
```env
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT=60
OPENAI_MAX_TOKENS=1200
OPENAI_TEMPERATURE=0.2
```

## 4) 서버 실행 방법
PowerShell:
```powershell
cd aouri-bot
python -m runtime.app
```

## 5) /api/ai/health 테스트 방법
```powershell
$base='http://127.0.0.1:8787'
Invoke-RestMethod "$base/api/ai/health"
```
기대:
- 키가 있으면 `enabled=true` + `ok=true` (또는 실패 시 원인)
- 키가 없으면 `enabled=false` (mock 동작)

## 6) 브라우저에서 /demo 테스트 방법
- `http://127.0.0.1:8787/demo`
- 흐름: 입력 → 질문(1개씩) → 결과(대표 결론 1개)

## 7) 키가 없을 때 동작 방식
- AI는 비활성화되고(mock provider),
- 기존 rule 기반 질문/검토/수정제안/초안 생성은 그대로 동작한다.

## 8) 절대 하면 안 되는 것
- 코드에 직접 키 넣기(하드코딩)
- Git에 `.env`/키 파일 올리기
- 채팅/메일/이슈에 키를 붙여넣기

