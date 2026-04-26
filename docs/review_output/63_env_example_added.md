# .env.example 추가

## 목적
- 초보자도 로컬에서 안전하게 환경변수를 설정할 수 있도록 예시 파일을 제공
- 실제 키는 절대 저장/커밋하지 않도록 placeholder만 포함

## 추가 파일
- Repo root: [.env.example](file:///c:/Users/FURSYS/Desktop/aouribot/.env.example)

## 포함 항목(placeholder)
- `OPENAI_API_KEY=YOUR_OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-4.1-mini`
- `OPENAI_TIMEOUT=60`
- `OPENAI_MAX_TOKENS=1200`
- `OPENAI_TEMPERATURE=0.2`

## 사용 방법(요약)
1) `.env.example`을 복사해 `.env` 생성  
2) `.env`에 실제 `OPENAI_API_KEY`를 입력(절대 Git에 올리지 않기)  
3) 서버 실행 후 `/api/ai/health`로 확인  

