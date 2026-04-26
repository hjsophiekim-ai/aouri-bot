# dotenv 탐색 경로/로딩 교정(115)

## 문제
- `.env`에 키가 있어도 런타임이 다른 위치의 `.env`를 읽거나, BOM/형식 문제로 키를 정상 파싱하지 못하면 `/api/ai/health`에서 `OPENAI_API_KEY not set`이 계속 발생할 수 있다.

## 조치
### 1) dotenv 탐색 경로를 명시적인 순서로 통일
- 탐색 순서
  - 현재 작업 디렉토리의 `.env`
  - 프로젝트 루트의 `.env`
  - 프로젝트 루트의 부모 폴더의 `.env`
  - 현재 작업 디렉토리의 `.env.local`
  - 프로젝트 루트의 `.env.local`
  - 프로젝트 루트의 부모 폴더의 `.env.local`
- 구현: [dotenv.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/dotenv.py)

### 2) AI/Law config 로더가 동일한 dotenv 로더를 사용하도록 정리
- OpenAI: [ai/config.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/config.py)
- 국가법령정보: [law/config.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/law/config.py)

### 3) 파싱 내구성 강화
- `export KEY=...` 형태 지원
- 키에 BOM이 붙은 경우(`\ufeffOPENAI_API_KEY`) 제거 후 인식
- 값 뒤 주석(`# ...`)이 붙은 경우(따옴표 없는 값) 주석 제거 후 인식

### 4) 진단 정보(값 미노출) 기록 지원
- dotenv 후보/로드된 파일 경로를 기록하고, 이후 디버그 엔드포인트에서 확인 가능하도록 상태를 유지한다.
- 구현: [dotenv.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/dotenv.py), [env_debug.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/env_debug.py)
