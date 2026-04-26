# .env 로딩 우선순위 고정(121)

## 원칙(요청 반영)
1. `aouri-bot/.env`가 있으면 최우선으로 로드
2. 없으면 프로젝트 상위 루트의 `.env` 로드
3. 그래도 없으면 process env 사용
4. 어떤 경로를 로드했는지 경로/boolean만 디버그 가능
5. 키 값 자체는 절대 출력 금지

## 구현
- dotenv 후보 경로 생성 시, `aouri-bot/.env(.local)`을 최우선으로 배치하도록 변경
  - 후보 순서(실제 코드 기준)
    - `aouri-bot/.env.local`
    - `aouri-bot/.env`
    - `repo_root/.env.local`
    - `repo_root/.env`
    - `cwd/.env.local`
    - `cwd/.env`
- 구현: [dotenv.py](file:///g:/다른%20컴퓨터/내%20노트북%20(2)/Desktop/aouribot/aouri-bot/runtime/ai/dotenv.py)

## 검증 방법
- `GET /api/debug/env-status`
  - `dotenv.loaded`가 실제로 어떤 파일을 읽었는지 확인
  - `OPENAI_API_KEY_present=true`인지 확인(값 미노출)
- `GET /api/ai/health`
  - enabled/provider/model 확인
- `/api/review/analyze`
  - 10초 내 응답 유지 + law_search 포함 확인
